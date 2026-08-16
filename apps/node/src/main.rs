use anyhow::{Context, Result};
use body_finder_core::{elect_coordinator, estimate_from_rssi, CapabilityProbe, CapabilityState, NodeAdvertisement, NodePosition, FABRIC_PORT, PROTOCOL_VERSION};
use std::{collections::{BTreeMap, HashMap}, env, fs::OpenOptions, io::{ErrorKind, Write}, net::{Ipv4Addr, SocketAddrV4, UdpSocket}, process::Command, thread, time::{Duration, Instant, SystemTime, UNIX_EPOCH}};

#[derive(Debug)]
struct Args {
    node_id: String,
    session_id: String,
    x: Option<f64>,
    y: Option<f64>,
    calibrate_secs: u64,
    record: Option<String>,
}

fn arg_value(name: &str) -> Option<String> {
    let mut it = env::args();
    while let Some(v) = it.next() { if v == name { return it.next(); } }
    None
}

fn parse_args() -> Args {
    let host = env::var("COMPUTERNAME").or_else(|_| env::var("HOSTNAME")).unwrap_or_else(|_| "node".into());
    Args {
        node_id: arg_value("--node").unwrap_or(host),
        session_id: arg_value("--session").unwrap_or_else(|| "body-finder-lab".into()),
        x: arg_value("--x").and_then(|x| x.parse().ok()),
        y: arg_value("--y").and_then(|x| x.parse().ok()),
        calibrate_secs: arg_value("--calibrate").and_then(|x| x.parse().ok()).unwrap_or(10),
        record: arg_value("--record"),
    }
}

fn output(cmd: &str, args: &[&str]) -> Option<String> {
    let out = Command::new(cmd).args(args).output().ok()?;
    if !out.status.success() { return None; }
    Some(String::from_utf8_lossy(&out.stdout).to_string())
}

#[cfg(target_os = "linux")]
fn wifi_rssi() -> Option<f64> {
    if let Some(iw) = output("iw", &["dev"]) {
        let iface = iw.lines().find_map(|l| l.trim().strip_prefix("Interface ")).map(str::to_string);
        if let Some(iface) = iface {
            if let Some(link) = output("iw", &["dev", &iface, "link"]) {
                for line in link.lines() {
                    let t = line.trim();
                    if let Some(rest) = t.strip_prefix("signal:") {
                        if let Some(v) = rest.trim().split_whitespace().next().and_then(|v| v.parse::<f64>().ok()) { return Some(v); }
                    }
                }
            }
        }
    }
    let txt = std::fs::read_to_string("/proc/net/wireless").ok()?;
    for line in txt.lines().skip(2) {
        let parts: Vec<_> = line.split_whitespace().collect();
        if parts.len() >= 4 { if let Ok(v) = parts[3].trim_end_matches('.').parse::<f64>() { return Some(v); } }
    }
    None
}

#[cfg(target_os = "windows")]
fn wifi_rssi() -> Option<f64> {
    let txt = output("netsh", &["wlan", "show", "interfaces"])?;
    for line in txt.lines() {
        let lower = line.to_ascii_lowercase();
        if lower.contains("signal") && line.contains('%') {
            let pct = line.split(':').nth(1)?.trim().trim_end_matches('%').trim().parse::<f64>().ok()?;
            return Some(-100.0 + pct / 2.0);
        }
    }
    None
}

#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn wifi_rssi() -> Option<f64> { None }

fn platform() -> (&'static str, f32) {
    #[cfg(target_os = "windows")]
    { return ("windows", 0.72); }
    #[cfg(target_os = "linux")]
    {
        if env::var("WSL_DISTRO_NAME").is_ok() || env::var("WSL_INTEROP").is_ok() { return ("wsl", 0.62); }
        return ("ubuntu-linux", 0.92);
    }
    #[allow(unreachable_code)]
    (env::consts::OS, 0.55)
}

fn capabilities(rssi: Option<f64>) -> BTreeMap<String, CapabilityProbe> {
    let mut c = BTreeMap::new();
    c.insert("wifi_rssi".into(), CapabilityProbe {
        state: if rssi.is_some() { CapabilityState::Working } else { CapabilityState::ProbeFailed },
        detail: if rssi.is_some() { "live OS Wi-Fi link metric read".into() } else { "no accessible Wi-Fi RSSI interface found".into() },
    });
    let bt_ok = if cfg!(target_os="linux") { output("bluetoothctl", &["show"]).is_some() } else { false };
    c.insert("ble".into(), CapabilityProbe {
        state: if bt_ok { CapabilityState::SupportedUnverified } else { CapabilityState::Unsupported },
        detail: if bt_ok { "BlueZ controller visible; active ranging not yet validated".into() } else { "BLE fabric adapter not active in this build".into() },
    });
    c.insert("csi".into(), CapabilityProbe { state: CapabilityState::Unsupported, detail: "no verified CSI plugin loaded; RSSI is never labeled CSI".into() });
    c.insert("compute".into(), CapabilityProbe { state: CapabilityState::Working, detail: "native Body Finder Rust node".into() });
    c
}

fn sample_baseline(secs: u64) -> (Option<f64>, Option<f64>) {
    eprintln!("CALIBRATION: keep the scan zone empty for {secs}s");
    let end = Instant::now() + Duration::from_secs(secs.max(3));
    let mut xs = Vec::new();
    while Instant::now() < end {
        if let Some(v) = wifi_rssi() { xs.push(v); }
        thread::sleep(Duration::from_millis(250));
    }
    if xs.len() < 3 { return (None, None); }
    let mean = xs.iter().sum::<f64>() / xs.len() as f64;
    let var = xs.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / xs.len() as f64;
    (Some(mean), Some(var.sqrt().max(1.0)))
}

fn main() -> Result<()> {
    let args = parse_args();
    let (plat, score) = platform();
    let (baseline, baseline_sigma) = sample_baseline(args.calibrate_secs);
    let started = Instant::now();
    let socket = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, FABRIC_PORT)).with_context(|| format!("bind UDP {FABRIC_PORT}"))?;
    socket.set_broadcast(true)?;
    socket.set_nonblocking(true)?;
    let group = Ipv4Addr::new(239, 255, 77, 77);
    let _ = socket.join_multicast_v4(&group, &Ipv4Addr::UNSPECIFIED);
    let broadcast = SocketAddrV4::new(Ipv4Addr::BROADCAST, FABRIC_PORT);
    let multicast = SocketAddrV4::new(group, FABRIC_PORT);
    let mut peers: HashMap<String, (NodeAdvertisement, Instant)> = HashMap::new();
    let mut recorder = match &args.record {
        Some(path) => Some(OpenOptions::new().create(true).append(true).open(path).with_context(|| format!("open record {path}"))?),
        None => None,
    };
    let pos = match (args.x, args.y) { (Some(x), Some(y)) => Some(NodePosition { x_m:x, y_m:y, z_m:0.0, sigma_m:0.25 }), _ => None };
    let mut buf = [0u8; 65_507];

    eprintln!("Body Finder node={} platform={} UDP={} baseline={:?} sigma={:?}", args.node_id, plat, FABRIC_PORT, baseline, baseline_sigma);
    loop {
        let rssi = wifi_rssi();
        let ad = NodeAdvertisement {
            protocol_version: PROTOCOL_VERSION,
            session_id: args.session_id.clone(),
            node_id: args.node_id.clone(),
            display_name: args.node_id.clone(),
            platform: plat.into(),
            monotonic_ns: started.elapsed().as_nanos() as u64,
            coordinator_score: score,
            capabilities: capabilities(rssi),
            rssi_dbm: rssi,
            baseline_rssi_dbm: baseline,
            baseline_sigma_db: baseline_sigma,
            position: pos.clone(),
            scanning: baseline.is_some(),
        };
        let payload = serde_json::to_vec(&ad)?;
        let _ = socket.send_to(&payload, broadcast);
        let _ = socket.send_to(&payload, multicast);

        loop {
            match socket.recv_from(&mut buf) {
                Ok((n, _)) => {
                    if let Ok(p) = serde_json::from_slice::<NodeAdvertisement>(&buf[..n]) {
                        if p.protocol_version == PROTOCOL_VERSION && p.session_id == args.session_id && p.node_id != args.node_id {
                            peers.insert(p.node_id.clone(), (p, Instant::now()));
                        }
                    }
                }
                Err(e) if e.kind() == ErrorKind::WouldBlock => break,
                Err(_) => break,
            }
        }
        peers.retain(|_, (_, seen)| seen.elapsed() < Duration::from_secs(5));
        let mut all: Vec<NodeAdvertisement> = peers.values().map(|(p,_)| p.clone()).collect();
        all.push(ad.clone());
        let coordinator = elect_coordinator(&all);
        let estimate = estimate_from_rssi(&all);
        let now_ms = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis();
        let event = serde_json::json!({
            "type":"status",
            "unix_ms": now_ms,
            "node": ad,
            "peer_count": peers.len(),
            "coordinator_node_id": coordinator,
            "human_estimate": estimate,
            "truth":"LIVE_OS_MEASUREMENTS_EXPERIMENTAL_LOCALIZATION"
        });
        let line = serde_json::to_string(&event)?;
        println!("{line}");
        if let Some(f) = recorder.as_mut() { writeln!(f, "{line}")?; f.flush()?; }
        thread::sleep(Duration::from_secs(1));
    }
}
