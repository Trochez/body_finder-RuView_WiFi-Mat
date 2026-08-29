use anyhow::{bail, Context, Result};
use body_finder_science::{canonical_measurements, deterministic_digest, read_measurements};
use std::{
    env,
    fs::File,
    io::{BufReader, Write},
};

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
        println!("body-finder-replay --input session.jsonl [--output canonical.jsonl]");
        return Ok(());
    }
    let input = value("--input").context("--input is required")?;
    let measurements = read_measurements(BufReader::new(
        File::open(&input).with_context(|| format!("open {input}"))?,
    ))?;
    if measurements.is_empty() {
        bail!("no measurements");
    }
    let digest = deterministic_digest(&measurements)?;
    let canonical = canonical_measurements(measurements);
    if let Some(output) = value("--output") {
        let mut f = File::create(output)?;
        for m in &canonical {
            writeln!(f, "{}", serde_json::to_string(m)?)?;
        }
    }
    let summary = serde_json::json!({"schema_version":1,"tool":"body-finder-replay","measurement_count":canonical.len(),"session_id":canonical[0].session_id,"first_monotonic_ns":canonical.first().map(|m|m.timestamp_monotonic_ns),"last_monotonic_ns":canonical.last().map(|m|m.timestamp_monotonic_ns),"deterministic_digest":digest,"simulation_is_physical_proof":false});
    println!("{}", serde_json::to_string_pretty(&summary)?);
    Ok(())
}
