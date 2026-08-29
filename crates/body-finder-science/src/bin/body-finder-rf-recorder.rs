use anyhow::{Context, Result};
use body_finder_science::{CapabilityTruth, EvidencePolicy, RFMeasurement, SessionManifest};
use std::{
    collections::BTreeMap,
    env,
    fs::File,
    io::Write,
    process::Command,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

fn arg(name: &str) -> Option<String> {
    let mut a = env::args();
    while let Some(x) = a.next() {
        if x == name {
            return a.next();
        }
    }
    None
}
fn cmd(c: &str, args: &[&str]) -> Option<String> {
    let o = Command::new(c).args(args).output().ok()?;
    if !o.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&o.stdout).to_string())
}
fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}
fn host() -> String {
    env::var("COMPUTERNAME")
        .or_else(|_| env::var("HOSTNAME"))
        .unwrap_or_else(|_| "node".into())
}
fn platform() -> String {
    #[cfg(target_os = "windows")]
    {
        return "windows-native".into();
    }
    #[cfg(target_os = "linux")]
    {
        if env::var("WSL_DISTRO_NAME").is_ok() || env::var("WSL_INTEROP").is_ok() {
            return "wsl-compute".into();
        }
        return "ubuntu-linux".into();
    }
    #[allow(unreachable_code)]
    env::consts::OS.into()
}

#[derive(Default)]
struct WifiSample {
    rssi: Option<f64>,
    bssid: Option<String>,
    frequency: Option<f64>,
    channel: Option<u32>,
    provenance: String,
}
#[cfg(target_os = "linux")]
fn wifi() -> WifiSample {
    let mut s = WifiSample {
        provenance: "linux iw connected-link".into(),
        ..Default::default()
    };
    let Some(dev) = cmd("iw", &["dev"]) else {
        return s;
    };
    let Some(iface) = dev
        .lines()
        .find_map(|l| l.trim().strip_prefix("Interface "))
        .map(str::to_string)
    else {
        return s;
    };
    let Some(link) = cmd("iw", &["dev", &iface, "link"]) else {
        return s;
    };
    for line in link.lines() {
        let t = line.trim();
        if let Some(v) = t
            .strip_prefix("signal:")
            .and_then(|x| x.split_whitespace().next())
            .and_then(|x| x.parse().ok())
        {
            s.rssi = Some(v)
        }
        if let Some(v) = t.strip_prefix("freq:").and_then(|x| x.trim().parse().ok()) {
            s.frequency = Some(v)
        }
        if let Some(v) = t
            .strip_prefix("Connected to ")
            .and_then(|x| x.split_whitespace().next())
        {
            s.bssid = Some(v.to_string())
        }
    }
    s
}
#[cfg(target_os = "windows")]
fn wifi() -> WifiSample {
    let mut s = WifiSample {
        provenance: "windows netsh wlan show interfaces".into(),
        ..Default::default()
    };
    let Some(text) = cmd("netsh", &["wlan", "show", "interfaces"]) else {
        return s;
    };
    for line in text.lines() {
        let l = line.trim();
        let low = l.to_ascii_lowercase();
        if low.starts_with("signal") && l.contains('%') {
            if let Some(v) = l
                .split(':')
                .nth(1)
                .and_then(|x| x.trim().trim_end_matches('%').parse::<f64>().ok())
            {
                s.rssi = Some(-100.0 + v / 2.0)
            }
        } else if low.starts_with("bssid") && !low.starts_with("bssid 0") {
            s.bssid = l
                .split(':')
                .skip(1)
                .collect::<Vec<_>>()
                .join(":")
                .trim()
                .to_string()
                .into()
        } else if low.starts_with("channel") {
            s.channel = l.split(':').nth(1).and_then(|x| x.trim().parse().ok())
        }
    }
    s
}
#[cfg(not(any(target_os = "linux", target_os = "windows")))]
fn wifi() -> WifiSample {
    WifiSample {
        provenance: "unsupported platform".into(),
        ..Default::default()
    }
}

fn main() -> Result<()> {
    if env::args().any(|a| a == "--help" || a == "-h") {
        println!("body-finder-rf-recorder --output rf.jsonl --manifest session-manifest.json [--session ID] [--node ID] [--duration 60] [--interval-ms 500]");
        return Ok(());
    }
    let output = arg("--output").context("--output required")?;
    let manifest_path = arg("--manifest").context("--manifest required")?;
    let session = arg("--session").unwrap_or_else(|| format!("session-{}", now_ms()));
    let node = arg("--node").unwrap_or_else(host);
    let duration: u64 = arg("--duration").and_then(|x| x.parse().ok()).unwrap_or(60);
    let interval: u64 = arg("--interval-ms")
        .and_then(|x| x.parse().ok())
        .unwrap_or(500)
        .max(100);
    let p = platform();
    let initial = wifi();
    let mut caps = BTreeMap::new();
    let wsl = p.starts_with("wsl");
    caps.insert(
        "wifi_connected_rssi".into(),
        CapabilityTruth {
            state: if initial.rssi.is_some() {
                "WORKING".into()
            } else if wsl {
                "UNSUPPORTED".into()
            } else {
                "PROBE_FAILED".into()
            },
            detail: if wsl {
                "WSL direct RF access is not claimed; run native Windows or Ubuntu collector".into()
            } else if initial.rssi.is_some() {
                initial.provenance.clone()
            } else {
                "no connected Wi-Fi RSSI sample available".into()
            },
        },
    );
    caps.insert("ble_scan".into(),CapabilityTruth{state:if p=="ubuntu-linux"&&cmd("bluetoothctl",&["show"]).is_some(){"SUPPORTED_UNVERIFIED".into()}else{"UNSUPPORTED".into()},detail:"dev-18 recorder does not fabricate BLE distance; Android BLE geometry remains authoritative when present".into()});
    caps.insert(
        "csi".into(),
        CapabilityTruth {
            state: "UNSUPPORTED".into(),
            detail: "no verified CSI plugin loaded".into(),
        },
    );
    let started_unix = now_ms();
    let start = Instant::now();
    let mut file = File::create(&output)?;
    let mut count = 0usize;
    while start.elapsed() < Duration::from_secs(duration) {
        let s = wifi();
        if let Some(rssi) = s.rssi {
            let m = RFMeasurement {
                schema_version: 1,
                timestamp_monotonic_ns: start.elapsed().as_nanos() as u64,
                timestamp_unix_ms: Some(now_ms()),
                source_node_id: node.clone(),
                peer_or_bssid: s
                    .bssid
                    .unwrap_or_else(|| "CONNECTED_WIFI_UNKNOWN_BSSID".into()),
                modality: "WIFI_CONNECTED_RSSI_DBM".into(),
                raw_value: rssi,
                variance: 0.0,
                quality: "MEDIUM".into(),
                position: None,
                orientation: None,
                frequency_mhz: s.frequency,
                channel: s.channel,
                capability_provenance: s.provenance,
                session_id: session.clone(),
                metadata: BTreeMap::new(),
            };
            writeln!(file, "{}", serde_json::to_string(&m)?)?;
            file.flush()?;
            count += 1
        }
        thread::sleep(Duration::from_millis(interval));
    }
    let manifest = SessionManifest {
        schema_version: 1,
        session_id: session,
        node_id: node,
        platform: p,
        software_build: "0.2.0-experimental.18".into(),
        started_unix_ms: started_unix,
        ended_unix_ms: Some(now_ms()),
        monotonic_origin: "PROCESS_START".into(),
        sample_interval_ms: interval,
        capabilities: caps,
        device_inventory: vec![],
        evidence_policy: EvidencePolicy::default(),
    };
    serde_json::to_writer_pretty(File::create(&manifest_path)?, &manifest)?;
    eprintln!("recorded {count} measurements -> {output}; manifest -> {manifest_path}");
    Ok(())
}
