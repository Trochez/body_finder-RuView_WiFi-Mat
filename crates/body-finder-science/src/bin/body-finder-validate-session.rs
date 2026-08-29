use anyhow::{Context, Result};
use body_finder_science::{
    deterministic_digest, read_measurements, validate_measurements, SessionManifest,
};
use std::{env, fs::File, io::BufReader, process};
fn value(name: &str) -> Option<String> {
    let mut a = env::args();
    while let Some(x) = a.next() {
        if x == name {
            return a.next();
        }
    }
    None
}
fn main() -> Result<()> {
    if env::args().any(|a| a == "--help" || a == "-h") {
        println!(
            "body-finder-validate-session --manifest session-manifest.json --input session.jsonl"
        );
        return Ok(());
    }
    let manifest_path = value("--manifest").context("--manifest is required")?;
    let input = value("--input").context("--input is required")?;
    let manifest: SessionManifest =
        serde_json::from_reader(BufReader::new(File::open(manifest_path)?))?;
    let measurements = read_measurements(BufReader::new(File::open(input)?))?;
    let result = validate_measurements(&manifest, &measurements);
    let report = match result {
        Ok(()) => {
            serde_json::json!({"schema_version":1,"gate":"dev18_session_integrity","pass":true,"session_id":manifest.session_id,"node_id":manifest.node_id,"measurement_count":measurements.len(),"deterministic_digest":deterministic_digest(&measurements)?})
        }
        Err(e) => {
            serde_json::json!({"schema_version":1,"gate":"dev18_session_integrity","pass":false,"session_id":manifest.session_id,"node_id":manifest.node_id,"measurement_count":measurements.len(),"error":e.to_string()})
        }
    };
    println!("{}", serde_json::to_string_pretty(&report)?);
    if report["pass"] == false {
        process::exit(2)
    }
    Ok(())
}
