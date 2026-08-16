use serde::{Deserialize, Serialize};

pub const RUVIEW_COMMIT: &str = "4685618388a5e49fad5b3005806f3bdd6a7c25c3";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RuViewAdapterStatus {
    pub pinned_commit: String,
    pub compiled_with_ruview: bool,
    pub local_physical_csi_validated: bool,
    pub truth_classification: String,
}

pub fn status() -> RuViewAdapterStatus {
    RuViewAdapterStatus {
        pinned_commit: RUVIEW_COMMIT.into(),
        compiled_with_ruview: cfg!(feature = "ruview"),
        local_physical_csi_validated: false,
        truth_classification: if cfg!(feature = "ruview") {
            "REAL_DEPENDENCY_COMPILED__LOCAL_PHYSICAL_CSI_UNVALIDATED".into()
        } else {
            "ADAPTER_PRESENT__RUVIEW_FEATURE_DISABLED".into()
        },
    }
}

#[cfg(feature = "ruview")]
pub fn compile_time_contract_probe() -> &'static str {
    // A direct type reference makes compatibility CI fail if WiFi-Mat stops exporting
    // the coordinator config type documented by the pinned upstream snapshot.
    std::any::type_name::<wifi_densepose_mat::DisasterConfig>()
}

#[cfg(not(feature = "ruview"))]
pub fn compile_time_contract_probe() -> &'static str {
    "wifi-densepose-mat feature disabled"
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn never_claims_local_csi_validation() {
        assert!(!status().local_physical_csi_validated);
        assert!(!compile_time_contract_probe().is_empty());
    }
}
