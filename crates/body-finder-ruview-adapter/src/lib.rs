use serde::{Deserialize, Serialize};

pub const RUVIEW_COMMIT: &str = "4685618388a5e49fad5b3005806f3bdd6a7c25c3";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RuViewAdapterStatus {
    pub pinned_commit: String,
    pub upstream_contract_checked_separately: bool,
    pub local_physical_csi_validated: bool,
    pub truth_classification: String,
}

pub fn status() -> RuViewAdapterStatus {
    RuViewAdapterStatus {
        pinned_commit: RUVIEW_COMMIT.into(),
        upstream_contract_checked_separately: true,
        local_physical_csi_validated: false,
        truth_classification: "PINNED_UPSTREAM_BOUNDARY__LOCAL_PHYSICAL_CSI_UNVALIDATED".into(),
    }
}

pub fn contract_probe() -> &'static str {
    "wifi-densepose-mat is compiled in the dedicated RuView Compatibility workflow"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn never_claims_local_csi_validation() {
        assert!(!status().local_physical_csi_validated);
        assert!(status().upstream_contract_checked_separately);
        assert!(!contract_probe().is_empty());
    }
}
