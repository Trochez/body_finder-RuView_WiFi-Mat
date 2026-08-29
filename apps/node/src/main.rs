use anyhow::{Context, Result};
use body_finder_core::{
    elect_coordinator, estimate_from_rssi_with_geometry, published_geometry_from_coordinator,
    solve_geometry, CapabilityProbe, CapabilityState, GeometrySolution, NodeAdvertisement,
    FABRIC_PORT, PROTOCOL_VERSION,
};
use std::{
    collections::{BTreeMap, HashMap},
    env,
    fs::OpenOptions,
    io::{ErrorKind, Write},
    net::{Ipv4Addr, SocketAddrV4, UdpSocket},
    process::Command,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

#[derive(Debug)]
struct Args {
    node_id: String,
    session_id: String,
    calibrate_secs: u64,
    record: Option<String>,
}

fn arg_value(name: &str) -> Option<String> {
    let mut args = env::args();
    while let Some(value) = args.next() {
        if value == name {
            return args.next();
        }
    }
    None
}

fn parse_args() -> Args {
    if env::args().any(|arg| arg == "--help" || arg == "-h") {
        println!(
            "Body Finder – RuView automatic-geometry node\n\nUSAGE:\n  body-finder-node [--node NAME] [--session ID] [--calibrate SECONDS] [--record FILE.jsonl]\n\nNode coordinates are never accepted in normal operation. Automatic geometry is solved only from real pairwise ranging observations received from capable peers. Ground-truth coordinates belong in the external validation file, not in this process."
        );
        std::process::exit(0);
    }
    let host = env::var("COMPUTERNAME")
        .or_else(|_| env::var("HOSTNAME"))
        .unwrap_or_else(|_| "node".into());
    Args {
        node_id: arg_value("--node").unwrap_or(host),
        session_id: arg_value("--session").unwrap_or_else(|| "body-finder-lab".into()),
        calibrate_secs: arg_value("--calibrate")
            .and_then(|value| value.parse().ok())
            .unwrap_or(10),
        record: arg_value("--record"),
    }
}

fn output(command: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(command).args(args).output().ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&output.stdout).to_string())
}

#[cfg(target_os = "linux")]
fn wifi_rssi() -> Option<f64> {
    if let Some(iw) = output("iw", &["dev"]) {
        let interface = iw
            .lines()
            .find_map(|line| line.trim().strip_prefix("Interface "))
            .map(str::to_string);
        if let Some(interface) = interface {
            if let Some(link) = output("iw", &["dev", &interface, "link"]) {
                for line in link.lines() {
                    let trimmed = line.trim();
                    if let Some(rest) = trimmed.strip_prefix("signal:") {
                        if let Some(value) = rest
                            .split_whitespace()
                            .next()
                            .and_then(|value| value.parse::<f64>().ok())
                        {
                            return Some(value);
                        }
                    }
                }
            }
        }
    }
    let text = std::fs::read_to_string("/proc/net/wireless").ok()?;
    for line in text.lines().skip(2) {
        let parts: Vec<_> = line.split_whitespace().collect();
        if parts.len() >= 4 {
            if let Ok(value) = parts[3].trim_end_matches('.').parse::<f64>() {
                return Some(value);
            }
        }
    }
    None
}

#[cfg(target_os = "windows")]
fn wifi_rssi() -> Option<f64> {
    let text = output("netsh", &["wlan", "show", "interfaces"])?;
    for line in text.lines() {
        let lower = line.to_ascii_lowercase();
        if lower.contains("signal") && line.contains('%') {
            let percent = line
                .split(':')
                .nth(1)?
                .trim()
                .trim_end_matches('%')
                .trim()
                .parse::<f64>()
                .ok()?;
            return Some(-100.0 + percent / 2.0);
        }
    }
    None
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn wifi_rssi() -> Option<f64> {
    None
}

fn platform() -> (&'static str, f32) {
    #[cfg(target_os = "windows")]
    {
        return ("windows", 0.72);
    }
    #[cfg(target_os = "linux")]
    {
        if env::var("WSL_DISTRO_NAME").is_ok() || env::var("WSL_INTEROP").is_ok() {
            return ("wsl", 0.62);
        }
        return ("ubuntu-linux", 0.92);
    }
    #[allow(unreachable_code)]
    (env::consts::OS, 0.55)
}

fn capabilities(rssi: Option<f64>, platform: &str) -> BTreeMap<String, CapabilityProbe> {
    let mut capabilities = BTreeMap::new();
    capabilities.insert(
        "wifi_rssi".into(),
        CapabilityProbe {
            state: if rssi.is_some() {
                CapabilityState::Working
            } else {
                CapabilityState::ProbeFailed
            },
            detail: if rssi.is_some() {
                "live OS connected-link Wi-Fi metric; human-presence evidence only, never inter-node distance".into()
            } else {
                "no accessible Wi-Fi RSSI interface found".into()
            },
        },
    );
    let bluetooth_visible =
        platform == "ubuntu-linux" && output("bluetoothctl", &["show"]).is_some();
    capabilities.insert(
        "ble_peer_ranging".into(),
        CapabilityProbe {
            state: if bluetooth_visible {
                CapabilityState::SupportedUnverified
            } else {
                CapabilityState::Unsupported
            },
            detail: if bluetooth_visible {
                "BlueZ controller visible; this release does not fabricate Linux BLE distance. Android peers may still provide real range edges.".into()
            } else if platform == "wsl" {
                "WSL has no verified direct BLE ranging adapter; compute/network role only".into()
            } else {
                "no verified native BLE ranging adapter active".into()
            },
        },
    );
    capabilities.insert(
        "automatic_geometry_compute".into(),
        CapabilityProbe {
            state: CapabilityState::Working,
            detail: "protocol-v2 source-aware automatic geometry solver active".into(),
        },
    );
    capabilities.insert(
        "geometry_publication".into(),
        CapabilityProbe {
            state: CapabilityState::Working,
            detail: "elected coordinator publishes its derived GeometrySolution revision; non-coordinators consume it when present".into(),
        },
    );
    capabilities.insert(
        "csi".into(),
        CapabilityProbe {
            state: CapabilityState::Unsupported,
            detail: "no verified CSI plugin loaded; RSSI is never labeled CSI".into(),
        },
    );
    capabilities.insert(
        "compute".into(),
        CapabilityProbe {
            state: CapabilityState::Working,
            detail: "native Body Finder Rust node".into(),
        },
    );
    capabilities
}

fn sample_baseline(seconds: u64) -> (Option<f64>, Option<f64>) {
    eprintln!("CALIBRATION: keep the scan zone empty for {seconds}s");
    let end = Instant::now() + Duration::from_secs(seconds.max(3));
    let mut samples = Vec::new();
    while Instant::now() < end {
        if let Some(value) = wifi_rssi() {
            samples.push(value);
        }
        thread::sleep(Duration::from_millis(250));
    }
    if samples.len() < 3 {
        return (None, None);
    }
    let mean = samples.iter().sum::<f64>() / samples.len() as f64;
    let variance = samples
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / samples.len() as f64;
    (Some(mean), Some(variance.sqrt().max(1.0)))
}

fn main() -> Result<()> {
    let args = parse_args();
    let (platform, coordinator_score) = platform();
    let (baseline, baseline_sigma) = sample_baseline(args.calibrate_secs);
    let started = Instant::now();
    let socket = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, FABRIC_PORT))
        .with_context(|| format!("bind UDP {FABRIC_PORT}"))?;
    socket.set_broadcast(true)?;
    socket.set_nonblocking(true)?;
    let group = Ipv4Addr::new(239, 255, 77, 77);
    let _ = socket.join_multicast_v4(&group, &Ipv4Addr::UNSPECIFIED);
    let broadcast = SocketAddrV4::new(Ipv4Addr::BROADCAST, FABRIC_PORT);
    let multicast = SocketAddrV4::new(group, FABRIC_PORT);
    let mut peers: HashMap<String, (NodeAdvertisement, Instant)> = HashMap::new();
    let mut recorder = match &args.record {
        Some(path) => Some(
            OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .with_context(|| format!("open record {path}"))?,
        ),
        None => None,
    };
    let mut buffer = [0_u8; 65_507];
    let mut geometry_to_publish: Option<GeometrySolution> = None;
    let mut previous_frame: Option<(String, u64)> = None;

    eprintln!(
        "Body Finder node={} platform={} protocol={} UDP={} baseline={:?} sigma={:?} geometry=AUTO",
        args.node_id, platform, PROTOCOL_VERSION, FABRIC_PORT, baseline, baseline_sigma
    );

    loop {
        let rssi = wifi_rssi();
        let advertisement = NodeAdvertisement {
            protocol_version: PROTOCOL_VERSION,
            session_id: args.session_id.clone(),
            node_id: args.node_id.clone(),
            display_name: args.node_id.clone(),
            platform: platform.into(),
            monotonic_ns: started.elapsed().as_nanos() as u64,
            coordinator_score,
            capabilities: capabilities(rssi, platform),
            rssi_dbm: rssi,
            baseline_rssi_dbm: baseline,
            baseline_sigma_db: baseline_sigma,
            position: None,
            scanning: baseline.is_some(),
            ble_identity: None,
            ranges: Vec::new(),
            manual_geometry_override: false,
            geometry_publisher_node_id: geometry_to_publish.as_ref().map(|_| args.node_id.clone()),
            published_geometry: geometry_to_publish.clone(),
        };
        let payload = serde_json::to_vec(&advertisement)?;
        let _ = socket.send_to(&payload, broadcast);
        let _ = socket.send_to(&payload, multicast);

        loop {
            match socket.recv_from(&mut buffer) {
                Ok((size, _)) => {
                    if let Ok(peer) = serde_json::from_slice::<NodeAdvertisement>(&buffer[..size]) {
                        if peer.protocol_version == PROTOCOL_VERSION
                            && peer.session_id == args.session_id
                            && peer.node_id != args.node_id
                        {
                            peers.insert(peer.node_id.clone(), (peer, Instant::now()));
                        }
                    }
                }
                Err(error) if error.kind() == ErrorKind::WouldBlock => break,
                Err(_) => break,
            }
        }
        peers.retain(|_, (_, seen)| seen.elapsed() < Duration::from_secs(5));

        let mut all_nodes: Vec<NodeAdvertisement> =
            peers.values().map(|(peer, _)| peer.clone()).collect();
        all_nodes.push(advertisement.clone());
        all_nodes.sort_by(|a, b| a.node_id.cmp(&b.node_id));

        let coordinator = elect_coordinator(&all_nodes);
        let locally_solved = solve_geometry(&all_nodes);
        let coordinator_published = coordinator.as_deref().and_then(|id| {
            if id == args.node_id {
                None
            } else {
                published_geometry_from_coordinator(&all_nodes, id)
            }
        });
        let (geometry, geometry_source) = if coordinator.as_deref() == Some(args.node_id.as_str()) {
            (locally_solved.clone(), "LOCAL_ELECTED_COORDINATOR")
        } else if let Some(published) = coordinator_published {
            (Some(published), "ELECTED_COORDINATOR_PUBLICATION")
        } else {
            (
                locally_solved.clone(),
                "LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION",
            )
        };

        geometry_to_publish = if coordinator.as_deref() == Some(args.node_id.as_str()) {
            locally_solved.clone()
        } else {
            None
        };

        let frame_change = geometry.as_ref().and_then(|current| {
            previous_frame.as_ref().and_then(|(old_frame, old_revision)| {
                if old_frame != &current.frame_id || *old_revision != current.revision {
                    Some(serde_json::json!({
                        "previous_frame_id": old_frame,
                        "previous_revision": old_revision,
                        "current_frame_id": current.frame_id,
                        "current_revision": current.revision,
                        "classification": if old_frame == &current.frame_id {"REVISION_UPDATE"} else {"EXPLICIT_REFRAME"}
                    }))
                } else {
                    None
                }
            })
        });
        if let Some(current) = &geometry {
            previous_frame = Some((current.frame_id.clone(), current.revision));
        }

        let estimate = geometry
            .as_ref()
            .and_then(|solution| estimate_from_rssi_with_geometry(&all_nodes, solution));
        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis();
        let event = serde_json::json!({
            "type":"status",
            "release":"dev-13",
            "build":"0.2.0-experimental.13",
            "report_version":15,
            "protocol_version":PROTOCOL_VERSION,
            "evidence_contract":{"schema":"dev13-node-jsonl-evidence-v1","screenshots_required":false,"json_self_contained":true,"record_flag":"--record FILE.jsonl"},
            "self_diagnostic":{"platform":platform,"udp_bound":true,"automatic_geometry":true,"manual_geometry_override":false,"human_scanning_enabled":false,"human_localization_validated":false,"rescue_use_validated":false},
            "unix_ms":now_ms,
            "node":advertisement,
            "all_nodes":all_nodes,
            "peer_count":peers.len(),
            "coordinator_node_id":coordinator,
            "geometry":geometry,
            "geometry_source":geometry_source,
            "frame_change":frame_change,
            "human_estimate":estimate,
            "manual_geometry_override":false,
            "truth":"LIVE_OS_MEASUREMENTS__PAIRWISE_RANGES_ONLY_WHEN_PEERS_REPORT_REAL_RANGING__COORDINATOR_GEOMETRY_PUBLICATION__AUTOGEOMETRY_EXPERIMENTAL"
        });
        let line = serde_json::to_string(&event)?;
        println!("{line}");
        if let Some(file) = recorder.as_mut() {
            writeln!(file, "{line}")?;
            file.flush()?;
        }
        thread::sleep(Duration::from_secs(1));
    }
}
