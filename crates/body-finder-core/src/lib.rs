use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};

pub const PROTOCOL_VERSION: u16 = 2;
pub const FABRIC_PORT: u16 = 47_777;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CapabilityState { Working, WorkingDegraded, SupportedUnverified, Unsupported, PermissionRequired, ProbeFailed }

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CapabilityProbe { pub state: CapabilityState, pub detail: String }

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum RangingTechnology { AndroidRangingUwb, AndroidRangingBleCs, AndroidRangingWifiNanRtt, AndroidRangingBleRssi, WifiRttAware, WifiRttAccessPoint, AndroidxUwb, BleRssi, LinuxAdapter, WindowsAdapter, Unknown }

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MeasurementQuality { High, Medium, Low, Rejected }
impl Default for MeasurementQuality { fn default() -> Self { Self::Low } }

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PairwiseRangeObservation {
    pub session_id: String, pub observer_node_id: String, pub peer_node_id: String,
    pub technology: RangingTechnology, pub monotonic_ns: u64,
    pub distance_m: Option<f64>, pub distance_sigma_m: Option<f64>,
    pub azimuth_deg: Option<f64>, pub azimuth_sigma_deg: Option<f64>,
    pub elevation_deg: Option<f64>, pub elevation_sigma_deg: Option<f64>,
    pub rssi_dbm: Option<f64>, #[serde(default)] pub quality: MeasurementQuality,
    pub source_detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct NodePosition { pub x_m: f64, pub y_m: f64, #[serde(default)] pub z_m: f64, #[serde(default = "default_position_sigma")] pub sigma_m: f64 }
fn default_position_sigma() -> f64 { 1.0 }

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NodeAdvertisement {
    pub protocol_version: u16, pub session_id: String, pub node_id: String, pub display_name: String,
    pub platform: String, pub monotonic_ns: u64, pub coordinator_score: f32,
    pub capabilities: BTreeMap<String, CapabilityProbe>, pub rssi_dbm: Option<f64>,
    pub baseline_rssi_dbm: Option<f64>, pub baseline_sigma_db: Option<f64>,
    /// Legacy/debug-only. Production automatic geometry never consumes this field.
    #[serde(default)] pub position: Option<NodePosition>, #[serde(default)] pub scanning: bool,
    #[serde(default)] pub ble_identity: Option<String>, #[serde(default)] pub ranges: Vec<PairwiseRangeObservation>,
    #[serde(default)] pub manual_geometry_override: bool,
}
impl NodeAdvertisement {
    pub fn anomaly_z(&self) -> Option<f64> {
        let current = self.rssi_dbm?; let baseline = self.baseline_rssi_dbm?;
        let sigma = self.baseline_sigma_db.unwrap_or(2.0).max(1.0);
        Some(((current - baseline).abs() / sigma).min(20.0))
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum GeometryState { DiscoveringNodes, Ranging, GeometryInsufficient, Geometry1d, Geometry2d, GeometryDegraded, GeometryStale }
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub enum GeometryDimension { #[serde(rename = "UNKNOWN")] Unknown, #[serde(rename = "1D")] OneD, #[serde(rename = "2D")] TwoD }

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NodePositionEstimate { pub node_id: String, pub x_m: f64, pub y_m: f64, pub z_m: f64, pub covariance_2x2: [[f64; 2]; 2], pub error_radius_95_m: f64 }
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RejectedEdge { pub edge_id: String, pub reason: String, pub residual_m: Option<f64> }
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GeometrySolution {
    pub frame_id: String, pub revision: u64, pub generated_monotonic_ns: u64,
    pub dimension: GeometryDimension, pub state: GeometryState,
    pub anchor_node_id: String, pub axis_node_id: Option<String>, pub positions: Vec<NodePositionEstimate>,
    pub residual_rms_m: Option<f64>, pub condition_score: Option<f64>, pub used_edges: Vec<String>,
    pub rejected_edges: Vec<RejectedEdge>, pub reason: Option<String>,
}

#[derive(Debug, Clone)]
struct Edge { id: String, a: String, b: String, distance: f64, sigma: f64, quality_weight: f64 }
fn quality_weight(q: &MeasurementQuality) -> f64 { match q { MeasurementQuality::High=>1.0, MeasurementQuality::Medium=>0.55, MeasurementQuality::Low=>0.18, MeasurementQuality::Rejected=>0.0 } }
fn median(mut xs: Vec<f64>) -> f64 { xs.sort_by(|a,b|a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)); let n=xs.len(); if n%2==0{(xs[n/2-1]+xs[n/2])/2.0}else{xs[n/2]} }
fn canonical_pair(a:&str,b:&str)->(String,String){if a<=b{(a.into(),b.into())}else{(b.into(),a.into())}}

fn collect_edges(nodes:&[NodeAdvertisement])->(Vec<Edge>,Vec<RejectedEdge>){
    let node_ids:BTreeSet<&str>=nodes.iter().map(|n|n.node_id.as_str()).collect();
    let mut grouped:BTreeMap<(String,String),Vec<&PairwiseRangeObservation>>=BTreeMap::new(); let mut rejected=Vec::new();
    for node in nodes { for obs in &node.ranges {
        let pair=canonical_pair(&obs.observer_node_id,&obs.peer_node_id); let edge_id=format!("{}::{}",pair.0,pair.1);
        if obs.session_id!=node.session_id || obs.observer_node_id!=node.node_id { rejected.push(RejectedEdge{edge_id,reason:"session/observer identity mismatch".into(),residual_m:None}); continue; }
        if !node_ids.contains(obs.peer_node_id.as_str()) || obs.peer_node_id==obs.observer_node_id { rejected.push(RejectedEdge{edge_id,reason:"peer not active in geometry graph".into(),residual_m:None}); continue; }
        let Some(d)=obs.distance_m else{continue}; let sigma=obs.distance_sigma_m.unwrap_or(3.0);
        if !d.is_finite() || !(0.05..=100.0).contains(&d) || !sigma.is_finite() || !(0.05..=30.0).contains(&sigma) || quality_weight(&obs.quality)<=0.0 { rejected.push(RejectedEdge{edge_id,reason:"invalid or rejected range sample".into(),residual_m:None}); continue; }
        grouped.entry(pair).or_default().push(obs);
    }}
    let mut edges=Vec::new();
    for ((a,b),samples) in grouped {
        let distances:Vec<f64>=samples.iter().filter_map(|o|o.distance_m).collect(); if distances.is_empty(){continue}
        let d=median(distances.clone()); let mad=median(distances.iter().map(|v|(v-d).abs()).collect());
        let reported=median(samples.iter().map(|o|o.distance_sigma_m.unwrap_or(3.0)).collect());
        let sigma=reported.max(1.4826*mad).max(0.15); let q=samples.iter().map(|o|quality_weight(&o.quality)).fold(0.0_f64,f64::max);
        edges.push(Edge{id:format!("{}::{}",a,b),a,b,distance:d,sigma,quality_weight:q});
    }
    (edges,rejected)
}

fn largest_component(node_ids:&[String],edges:&[Edge])->Vec<String>{
    let mut adjacency:HashMap<&str,Vec<&str>>=HashMap::new(); for e in edges{adjacency.entry(&e.a).or_default().push(&e.b);adjacency.entry(&e.b).or_default().push(&e.a)}
    let mut seen=BTreeSet::new(); let mut best=Vec::new();
    for id in node_ids { if seen.contains(id.as_str()){continue} let mut q=VecDeque::from([id.as_str()]);let mut comp=Vec::new();seen.insert(id.as_str());
        while let Some(cur)=q.pop_front(){comp.push(cur.to_string());for next in adjacency.get(cur).into_iter().flatten(){if seen.insert(*next){q.push_back(next)}}}
        comp.sort();if comp.len()>best.len()||(comp.len()==best.len()&&comp<best){best=comp}
    } best
}
fn edge_lookup<'a>(edges:&'a[Edge],a:&str,b:&str)->Option<&'a Edge>{let(x,y)=canonical_pair(a,b);edges.iter().find(|e|e.a==x&&e.b==y)}
fn weighted_degree(id:&str,edges:&[Edge])->f64{edges.iter().filter(|e|e.a==id||e.b==id).map(|e|e.quality_weight/(e.sigma*e.sigma).max(0.02)).sum()}
fn best_anchor(component:&[String],edges:&[Edge])->String{component.iter().cloned().max_by(|a,b|weighted_degree(a,edges).partial_cmp(&weighted_degree(b,edges)).unwrap_or(std::cmp::Ordering::Equal).then_with(||b.cmp(a))).unwrap_or_default()}
fn best_axis(anchor:&str,component:&[String],edges:&[Edge])->Option<String>{component.iter().filter(|id|id.as_str()!=anchor&&edge_lookup(edges,anchor,id).is_some()).cloned().max_by(|a,b|{let ea=edge_lookup(edges,anchor,a).unwrap();let eb=edge_lookup(edges,anchor,b).unwrap();let wa=ea.quality_weight/(ea.sigma*ea.sigma).max(0.02);let wb=eb.quality_weight/(eb.sigma*eb.sigma).max(0.02);wa.partial_cmp(&wb).unwrap_or(std::cmp::Ordering::Equal).then_with(||b.cmp(a))})}

fn initialize_positions(component:&[String],edges:&[Edge],anchor:&str,axis:&str)->Option<(BTreeMap<String,(f64,f64)>,String)>{
    let d_ab=edge_lookup(edges,anchor,axis)?.distance;let mut pos=BTreeMap::new();pos.insert(anchor.into(),(0.0,0.0));pos.insert(axis.into(),(d_ab,0.0));
    let mut best_third:Option<(String,f64,f64,f64)>=None;
    for c in component.iter().filter(|c|c.as_str()!=anchor&&c.as_str()!=axis){let Some(ac)=edge_lookup(edges,anchor,c)else{continue};let Some(bc)=edge_lookup(edges,axis,c)else{continue};let x=(ac.distance.powi(2)+d_ab.powi(2)-bc.distance.powi(2))/(2.0*d_ab.max(1e-6));let y2=ac.distance.powi(2)-x.powi(2);if y2<=0.0{continue}let y=y2.sqrt();let leverage=y/ac.distance.max(bc.distance).max(d_ab).max(0.1);if best_third.as_ref().map(|v|leverage>v.3).unwrap_or(true){best_third=Some((c.clone(),x,y,leverage))}}
    let(third,x,y,leverage)=best_third?;if leverage<0.06{return None}pos.insert(third.clone(),(x,y));
    loop{let mut added=false;for id in component{if pos.contains_key(id){continue}let neighbors:Vec<(String,&Edge)>=pos.keys().filter_map(|known|edge_lookup(edges,id,known).map(|e|(known.clone(),e))).collect();if neighbors.len()<2{continue}let(k1,e1)=&neighbors[0];let mut best:Option<(f64,f64,f64)>=None;
        for(k2,e2)in neighbors.iter().skip(1){let p1=pos[k1];let p2=pos[k2];let dx=p2.0-p1.0;let dy=p2.1-p1.1;let base=(dx*dx+dy*dy).sqrt();if base<0.05{continue}let along=(e1.distance.powi(2)+base.powi(2)-e2.distance.powi(2))/(2.0*base);let h2=e1.distance.powi(2)-along.powi(2);if h2<0.0{continue}let h=h2.sqrt();let ux=dx/base;let uy=dy/base;for sign in[1.0_f64,-1.0_f64]{let cx=p1.0+along*ux-sign*h*uy;let cy=p1.1+along*uy+sign*h*ux;let score=neighbors.iter().map(|(k,e)|{let pk=pos[k];(((cx-pk.0).powi(2)+(cy-pk.1).powi(2)).sqrt()-e.distance).abs()/e.sigma.max(0.15)}).sum::<f64>();if best.as_ref().map(|v|score<v.2).unwrap_or(true){best=Some((cx,cy,score))}}}
        if let Some((cx,cy,_))=best{pos.insert(id.clone(),(cx,cy));added=true}}
        if !added{break}
    }Some((pos,third))
}

fn optimize_positions(pos:&mut BTreeMap<String,(f64,f64)>,edges:&[Edge],anchor:&str,axis:&str,third:&str){
    for _ in 0..180{let mut deltas:HashMap<String,(f64,f64,f64)>=HashMap::new();let mut max_step=0.0_f64;
        for e in edges{let(Some(pa),Some(pb))=(pos.get(&e.a).copied(),pos.get(&e.b).copied())else{continue};let dx=pb.0-pa.0;let dy=pb.1-pa.1;let pred=(dx*dx+dy*dy).sqrt().max(1e-6);let residual=pred-e.distance;let robust=residual.clamp(-2.0*e.sigma.max(0.25),2.0*e.sigma.max(0.25));let strength=(e.quality_weight/(e.sigma*e.sigma).max(0.04)).clamp(0.02,20.0);let correction=robust*(0.20*strength/(1.0+strength));let ux=dx/pred;let uy=dy/pred;let af=e.a==anchor||e.a==axis;let bf=e.b==anchor||e.b==axis;let share=if af||bf{1.0}else{0.5};if !af{let v=deltas.entry(e.a.clone()).or_insert((0.0,0.0,0.0));v.0+=correction*ux*share;v.1+=correction*uy*share;v.2+=1.0}if !bf{let v=deltas.entry(e.b.clone()).or_insert((0.0,0.0,0.0));v.0-=correction*ux*share;v.1-=correction*uy*share;v.2+=1.0}}
        for(id,(sx,sy,count))in deltas{if count<=0.0{continue}if let Some(p)=pos.get_mut(&id){let dx=sx/count;let dy=sy/count;p.0+=dx;p.1+=dy;max_step=max_step.max((dx*dx+dy*dy).sqrt())}}if let Some(p)=pos.get_mut(third){p.1=p.1.abs()}if max_step<1e-5{break}
    }
}
fn revision_hash(edges:&[Edge])->u64{let mut h=0xcbf29ce484222325_u64;for e in edges{for b in format!("{}:{:.3}:{:.3};",e.id,e.distance,e.sigma).as_bytes(){h^=*b as u64;h=h.wrapping_mul(0x100000001b3)}}h}

pub fn solve_geometry(nodes:&[NodeAdvertisement])->Option<GeometrySolution>{
    if nodes.is_empty(){return None}let mut node_ids:Vec<String>=nodes.iter().map(|n|n.node_id.clone()).collect();node_ids.sort();node_ids.dedup();let generated=nodes.iter().map(|n|n.monotonic_ns).max().unwrap_or(0);
    let(all_edges,mut rejected)=collect_edges(nodes);let component=largest_component(&node_ids,&all_edges);let component_set:BTreeSet<&str>=component.iter().map(String::as_str).collect();let mut edges:Vec<Edge>=all_edges.into_iter().filter(|e|component_set.contains(e.a.as_str())&&component_set.contains(e.b.as_str())).collect();edges.sort_by(|a,b|a.id.cmp(&b.id));let anchor=if component.is_empty(){node_ids[0].clone()}else{best_anchor(&component,&edges)};
    if component.len()<2||edges.is_empty(){return Some(GeometrySolution{frame_id:format!("bf2-{anchor}"),revision:revision_hash(&edges),generated_monotonic_ns:generated,dimension:GeometryDimension::Unknown,state:GeometryState::GeometryInsufficient,anchor_node_id:anchor,axis_node_id:None,positions:vec![],residual_rms_m:None,condition_score:None,used_edges:vec![],rejected_edges:rejected,reason:Some("No defensible inter-node distance edge yet".into())})}
    let axis=best_axis(&anchor,&component,&edges)?;let axis_edge=edge_lookup(&edges,&anchor,&axis)?;let var=axis_edge.sigma.powi(2);let axis_positions=vec![NodePositionEstimate{node_id:anchor.clone(),x_m:0.0,y_m:0.0,z_m:0.0,covariance_2x2:[[var,0.0],[0.0,var]],error_radius_95_m:2.4477*axis_edge.sigma},NodePositionEstimate{node_id:axis.clone(),x_m:axis_edge.distance,y_m:0.0,z_m:0.0,covariance_2x2:[[var,0.0],[0.0,var]],error_radius_95_m:2.4477*axis_edge.sigma}];
    if component.len()<3||edges.len()<(2*component.len()).saturating_sub(3){return Some(GeometrySolution{frame_id:format!("bf2-{anchor}-{axis}"),revision:revision_hash(&edges),generated_monotonic_ns:generated,dimension:GeometryDimension::OneD,state:GeometryState::Geometry1d,anchor_node_id:anchor,axis_node_id:Some(axis),positions:axis_positions,residual_rms_m:Some(0.0),condition_score:Some(0.0),used_edges:vec![axis_edge.id.clone()],rejected_edges:rejected,reason:Some("Only a 1D baseline is observable; more independent range edges are required for 2D".into())})}
    let Some((mut pos,third))=initialize_positions(&component,&edges,&anchor,&axis)else{return Some(GeometrySolution{frame_id:format!("bf2-{anchor}-{axis}"),revision:revision_hash(&edges),generated_monotonic_ns:generated,dimension:GeometryDimension::OneD,state:GeometryState::GeometryInsufficient,anchor_node_id:anchor,axis_node_id:Some(axis),positions:axis_positions,residual_rms_m:None,condition_score:Some(0.0),used_edges:vec![axis_edge.id.clone()],rejected_edges:rejected,reason:Some("Range graph is degenerate or nearly collinear; refusing to manufacture a 2D layout".into())})};
    optimize_positions(&mut pos,&edges,&anchor,&axis,&third);
    let mut kept=Vec::new();for e in &edges{let(Some(a),Some(b))=(pos.get(&e.a),pos.get(&e.b))else{continue};let residual=(((a.0-b.0).powi(2)+(a.1-b.1).powi(2)).sqrt()-e.distance).abs();let threshold=(3.0*e.sigma).max(1.0).max(0.35*e.distance);if residual>threshold{rejected.push(RejectedEdge{edge_id:e.id.clone(),reason:"persistent solver outlier".into(),residual_m:Some(residual)})}else{kept.push(e.clone())}}
    if kept.len()>=(2*pos.len()).saturating_sub(3)&&kept.len()<edges.len(){edges=kept;optimize_positions(&mut pos,&edges,&anchor,&axis,&third)}
    let residuals:Vec<f64>=edges.iter().filter_map(|e|{let a=pos.get(&e.a)?;let b=pos.get(&e.b)?;Some(((a.0-b.0).powi(2)+(a.1-b.1).powi(2)).sqrt()-e.distance)}).collect();let residual_rms=if residuals.is_empty(){None}else{Some((residuals.iter().map(|r|r*r).sum::<f64>()/residuals.len() as f64).sqrt())};
    let values:Vec<_>=pos.values().copied().collect();let mut max_span=0.1_f64;let mut max_cross=0.0_f64;for i in 0..values.len(){for j in i+1..values.len(){max_span=max_span.max(((values[i].0-values[j].0).powi(2)+(values[i].1-values[j].1).powi(2)).sqrt());for k in j+1..values.len(){let a=values[i];let b=values[j];let c=values[k];max_cross=max_cross.max(((b.0-a.0)*(c.1-a.1)-(b.1-a.1)*(c.0-a.0)).abs())}}}let condition=(max_cross/(max_span*max_span)/0.35).clamp(0.0,1.0);let rms=residual_rms.unwrap_or(0.0);let disconnected=pos.len()<node_ids.len();let degraded=disconnected||condition<0.18||rms>2.5;
    let mut estimates=Vec::new();for(id,(x,y))in &pos{let info=edges.iter().filter(|e|e.a==*id||e.b==*id).map(|e|e.quality_weight/(e.sigma*e.sigma).max(0.04)).sum::<f64>();let sigma=(1.0/info.max(0.05)).sqrt().max(0.15)+rms*0.5+(1.0-condition)*0.5;estimates.push(NodePositionEstimate{node_id:id.clone(),x_m:*x,y_m:*y,z_m:0.0,covariance_2x2:[[sigma*sigma,0.0],[0.0,sigma*sigma]],error_radius_95_m:2.4477*sigma})}estimates.sort_by(|a,b|a.node_id.cmp(&b.node_id));
    let reason=if disconnected{Some(format!("Solved {}/{} active nodes; disconnected/unobservable nodes remain unresolved",pos.len(),node_ids.len()))}else if condition<0.18{Some("Geometry is poorly conditioned / nearly collinear".into())}else if rms>2.5{Some("Range residuals exceed the reliable geometry threshold".into())}else{None};
    Some(GeometrySolution{frame_id:format!("bf2-{anchor}-{axis}"),revision:revision_hash(&edges),generated_monotonic_ns:generated,dimension:GeometryDimension::TwoD,state:if degraded{GeometryState::GeometryDegraded}else{GeometryState::Geometry2d},anchor_node_id:anchor,axis_node_id:Some(axis),positions:estimates,residual_rms_m:residual_rms,condition_score:Some(condition),used_edges:edges.iter().map(|e|e.id.clone()).collect(),rejected_edges:rejected,reason})
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidenceContribution { pub node_id:String,pub source:String,pub anomaly_z:f64,pub weight:f64 }
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HumanEstimate { pub method:String,pub state:String,pub x_m:f64,pub y_m:f64,pub z_m:f64,pub range_m:f64,pub bearing_deg:f64,pub human_confidence:f64,pub uncertainty_percent:f64,pub error_radius_95_m:f64,pub evidence_quality:String,pub covariance_2x2:[[f64;2];2],pub provenance:Vec<EvidenceContribution> }

pub fn estimate_from_rssi_with_geometry(nodes:&[NodeAdvertisement],geometry:&GeometrySolution)->Option<HumanEstimate>{
    if !matches!(geometry.dimension,GeometryDimension::TwoD)||matches!(geometry.state,GeometryState::GeometryInsufficient|GeometryState::GeometryStale){return None}let positions:HashMap<&str,&NodePositionEstimate>=geometry.positions.iter().map(|p|(p.node_id.as_str(),p)).collect();let mut usable=Vec::new();for n in nodes{if !n.scanning{continue}let Some(p)=positions.get(n.node_id.as_str()).copied()else{continue};let Some(z)=n.anomaly_z()else{continue};if z>=0.75{usable.push((n,p,z))}}if usable.len()<3{return None}let sum_w:f64=usable.iter().map(|(_,_,z)|(z-0.5).max(0.1)).sum();if sum_w<=0.0{return None}let x=usable.iter().map(|(_,p,z)|p.x_m*(z-0.5).max(0.1)).sum::<f64>()/sum_w;let y=usable.iter().map(|(_,p,z)|p.y_m*(z-0.5).max(0.1)).sum::<f64>()/sum_w;let var_x=usable.iter().map(|(_,p,z)|{let w=(z-0.5).max(0.1);w*((p.x_m-x).powi(2)+p.covariance_2x2[0][0])}).sum::<f64>()/sum_w;let var_y=usable.iter().map(|(_,p,z)|{let w=(z-0.5).max(0.1);w*((p.y_m-y).powi(2)+p.covariance_2x2[1][1])}).sum::<f64>()/sum_w;let penalty=geometry.residual_rms_m.unwrap_or(1.0)+1.5*(1.0-geometry.condition_score.unwrap_or(0.0));let sigma_radial=(var_x+var_y).sqrt().max(0.5)+0.5*penalty;let error95=(2.4477*sigma_radial).max(1.0);let range=(x*x+y*y).sqrt();let uncertainty=(100.0*error95/range.max(2.0)).clamp(0.0,100.0);let mean_z=usable.iter().map(|(_,_,z)|*z).sum::<f64>()/usable.len() as f64;let confidence=(1.0-(-0.35*(mean_z-0.75).max(0.0)).exp()).clamp(0.0,0.95);let state=if mean_z>=5.0{"PROBABLE_HUMAN"}else{"POSSIBLE_HUMAN"};let quality=if uncertainty<=20.0{"HIGH"}else if uncertainty<=40.0{"MEDIUM"}else if uncertainty<=70.0{"LOW"}else{"VERY_LOW"};Some(HumanEstimate{method:"EXPERIMENTAL_RSSI_DISTURBANCE_AUTOGEOMETRY_V2".into(),state:state.into(),x_m:x,y_m:y,z_m:0.0,range_m:range,bearing_deg:x.atan2(y).to_degrees(),human_confidence:confidence,uncertainty_percent:uncertainty,error_radius_95_m:error95,evidence_quality:quality.into(),covariance_2x2:[[var_x,0.0],[0.0,var_y]],provenance:usable.into_iter().map(|(n,_,z)|EvidenceContribution{node_id:n.node_id.clone(),source:"WIFI_RSSI_DISTURBANCE".into(),anomaly_z:z,weight:(z-0.5).max(0.1)/sum_w}).collect()})
}
pub fn estimate_from_rssi(nodes:&[NodeAdvertisement])->Option<HumanEstimate>{let g=solve_geometry(nodes)?;estimate_from_rssi_with_geometry(nodes,&g)}
pub fn elect_coordinator(nodes:&[NodeAdvertisement])->Option<String>{nodes.iter().max_by(|a,b|a.coordinator_score.partial_cmp(&b.coordinator_score).unwrap_or(std::cmp::Ordering::Equal).then_with(||b.node_id.cmp(&a.node_id))).map(|n|n.node_id.clone())}

#[cfg(test)] mod tests{use super::*;fn obs(a:&str,b:&str,d:f64)->PairwiseRangeObservation{PairwiseRangeObservation{session_id:"test".into(),observer_node_id:a.into(),peer_node_id:b.into(),technology:RangingTechnology::BleRssi,monotonic_ns:1,distance_m:Some(d),distance_sigma_m:Some(0.25),azimuth_deg:None,azimuth_sigma_deg:None,elevation_deg:None,elevation_sigma_deg:None,rssi_dbm:Some(-60.0),quality:MeasurementQuality::Medium,source_detail:"fixture".into()}}fn node(id:&str,ranges:Vec<PairwiseRangeObservation>,rssi:f64)->NodeAdvertisement{NodeAdvertisement{protocol_version:PROTOCOL_VERSION,session_id:"test".into(),node_id:id.into(),display_name:id.into(),platform:"test".into(),monotonic_ns:1,coordinator_score:0.5,capabilities:BTreeMap::new(),rssi_dbm:Some(rssi),baseline_rssi_dbm:Some(-50.0),baseline_sigma_db:Some(1.0),position:None,scanning:true,ble_identity:None,ranges,manual_geometry_override:false}}fn triangle()->Vec<NodeAdvertisement>{vec![node("a",vec![obs("a","b",3.0),obs("a","c",4.0)],-60.0),node("b",vec![obs("b","a",3.0),obs("b","c",5.0)],-58.0),node("c",vec![obs("c","a",4.0),obs("c","b",5.0)],-56.0)]}#[test]fn two_nodes_are_only_1d(){let ns=vec![node("a",vec![obs("a","b",2.0)],-60.0),node("b",vec![obs("b","a",2.0)],-60.0)];let g=solve_geometry(&ns).unwrap();assert_eq!(g.dimension,GeometryDimension::OneD);assert_eq!(g.positions.len(),2)}#[test]fn triangle_solves_without_manual_coordinates(){let g=solve_geometry(&triangle()).unwrap();assert_eq!(g.dimension,GeometryDimension::TwoD);assert_eq!(g.positions.len(),3);assert!(g.positions.iter().all(|p|p.error_radius_95_m>0.0))}#[test]fn human_estimate_consumes_auto_geometry(){let ns=triangle();let g=solve_geometry(&ns).unwrap();let e=estimate_from_rssi_with_geometry(&ns,&g).unwrap();assert!(e.method.contains("AUTOGEOMETRY"));assert_eq!(e.provenance.len(),3)}#[test]fn protocol_round_trip(){let mut ns=triangle();let n=ns.remove(0);let s=serde_json::to_string(&n).unwrap();let decoded:NodeAdvertisement=serde_json::from_str(&s).unwrap();assert_eq!(decoded,n)}}
