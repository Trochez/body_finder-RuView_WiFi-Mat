use std::{
    env, fs,
    io::{self, Read},
};
fn main() {
    let mut s = String::new();
    if let Some(p) = env::args().nth(1) {
        s = fs::read_to_string(p).expect("read detector input")
    } else {
        io::stdin().read_to_string(&mut s).expect("read stdin");
    }
    match body_finder_science::human_detector::evaluate_json(&s) {
        Ok(v) => println!("{}", v),
        Err(e) => {
            eprintln!("{}", e);
            std::process::exit(2)
        }
    }
}
