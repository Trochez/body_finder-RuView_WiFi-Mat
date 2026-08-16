import React, { useEffect, useMemo, useState } from 'react';
import {
  SafeAreaView, View, Text, StyleSheet, Pressable, TextInput, ScrollView,
  Share, Platform, PermissionsAndroid,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import BodyFinderNative from './modules/body-finder-native';

type Pos = { x_m:number; y_m:number; z_m?:number; sigma_m?:number };
type Ad = {
  protocol_version:number; session_id:string; node_id:string; display_name:string; platform:string;
  coordinator_score:number; rssi_dbm:number|null; baseline_rssi_dbm:number|null; baseline_sigma_db:number|null;
  position:Pos|null; scanning:boolean; capabilities?:Record<string,unknown>;
};
type Estimate = {
  x_m:number; y_m:number; range_m:number; bearing_deg:number; human_confidence:number;
  uncertainty_percent:number; error_radius_95_m:number; quality:string; method:string; state:string;
};

const T = {
  en: {
    title:'Body Finder – RuView', experimental:'EXPERIMENTAL COMMON-DEVICE RF — NOT VALIDATED FOR RESCUE USE',
    radar:'Radar', expert:'Expert', calibrate:'Calibrate empty scene', scanning:'Start scan', stop:'Stop scan', peers:'nodes',
    pos:'This node position in array (meters)', share:'Share result JSON', empty:'Keep the target area empty while calibrating.',
    noTarget:'No defensible position yet. Need ≥3 calibrated, scanning nodes with known positions and measurable RF disturbance.',
    uncertainty:'position uncertainty', confidence:'human confidence', network:'OPEN / UNTRUSTED FIELD NETWORK',
    evidence:'Evidence: commodity Wi-Fi RSSI disturbance (not CSI)', set:'Set position', relative:'POSITION RELATIVE TO THIS DEVICE'
  },
  es: {
    title:'Body Finder – RuView', experimental:'RF DE DISPOSITIVOS COMUNES EXPERIMENTAL — NO VALIDADO PARA USO DE RESCATE',
    radar:'Radar', expert:'Experto', calibrate:'Calibrar escena vacía', scanning:'Iniciar escaneo', stop:'Detener escaneo', peers:'nodos',
    pos:'Posición de este nodo en el array (metros)', share:'Compartir resultado JSON', empty:'Mantén vacía el área objetivo durante la calibración.',
    noTarget:'Aún no hay posición defendible. Se necesitan ≥3 nodos calibrados, escaneando, con posición conocida y perturbación RF medible.',
    uncertainty:'incertidumbre de posición', confidence:'confianza humana', network:'RED DE CAMPO ABIERTA / NO CONFIABLE',
    evidence:'Evidencia: perturbación RSSI Wi-Fi commodity (no CSI)', set:'Guardar posición', relative:'POSICIÓN RELATIVA A ESTE DISPOSITIVO'
  }
};

function qualityFor(uncertainty:number) {
  return uncertainty<=20?'HIGH':uncertainty<=40?'MEDIUM':uncertainty<=70?'LOW':'VERY_LOW';
}

function estimateArray(nodes: Ad[]): Estimate | null {
  const usable = nodes.map(n => {
    if (!n.scanning || !n.position || n.rssi_dbm == null || n.baseline_rssi_dbm == null) return null;
    const sigma = Math.max(n.baseline_sigma_db ?? 2, 1);
    const z = Math.min(Math.abs(n.rssi_dbm - n.baseline_rssi_dbm) / sigma, 20);
    if (z < 0.75) return null;
    return { n, z, w:Math.max(z - .5,.1) };
  }).filter(Boolean) as {n:Ad;z:number;w:number}[];
  if (usable.length < 3) return null;
  const sw = usable.reduce((a,u)=>a+u.w,0);
  const x = usable.reduce((a,u)=>a+u.n.position!.x_m*u.w,0)/sw;
  const y = usable.reduce((a,u)=>a+u.n.position!.y_m*u.w,0)/sw;
  const vx = usable.reduce((a,u)=>a+u.w*((u.n.position!.x_m-x)**2+(u.n.position!.sigma_m??.25)**2),0)/sw;
  const vy = usable.reduce((a,u)=>a+u.w*((u.n.position!.y_m-y)**2+(u.n.position!.sigma_m??.25)**2),0)/sw;
  const error = Math.max(1,2.4477*Math.sqrt(vx+vy));
  const range = Math.hypot(x,y);
  const uncertainty = Math.max(0,Math.min(100,100*error/Math.max(range,2)));
  const meanZ = usable.reduce((a,u)=>a+u.z,0)/usable.length;
  const confidence = Math.max(0,Math.min(.95,1-Math.exp(-.35*Math.max(meanZ-.75,0))));
  return {
    x_m:x,y_m:y,range_m:range,bearing_deg:Math.atan2(x,y)*180/Math.PI,
    human_confidence:confidence,uncertainty_percent:uncertainty,error_radius_95_m:error,
    quality:qualityFor(uncertainty),method:'EXPERIMENTAL_RSSI_DISTURBANCE_CENTROID_V1',
    state:meanZ>=5?'PROBABLE_HUMAN':'POSSIBLE_HUMAN'
  };
}

function relativeToLocal(raw:Estimate|null, localPos:Pos|null|undefined):Estimate|null {
  if (!raw) return null;
  if (!localPos) return raw;
  const x = raw.x_m-localPos.x_m;
  const y = raw.y_m-localPos.y_m;
  const range = Math.hypot(x,y);
  const uncertainty = Math.max(0,Math.min(100,100*raw.error_radius_95_m/Math.max(range,2)));
  return {...raw,x_m:x,y_m:y,range_m:range,bearing_deg:Math.atan2(x,y)*180/Math.PI,
    uncertainty_percent:uncertainty,quality:qualityFor(uncertainty)};
}

const sleep=(ms:number)=>new Promise(r=>setTimeout(r,ms));

async function requestAndroidPermissions() {
  if (Platform.OS!=='android') return;
  const perms:any[]=[PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
  if (Number(Platform.Version)>=33) perms.push(PermissionsAndroid.PERMISSIONS.NEARBY_WIFI_DEVICES);
  try { await PermissionsAndroid.requestMultiple(perms); } catch { /* capability probe reports failure */ }
}

export default function App() {
  const [lang,setLang]=useState<'en'|'es'>('en');
  const [mode,setMode]=useState<'radar'|'expert'>('radar');
  const [caps,setCaps]=useState<any>({});
  const [local,setLocal]=useState<Ad|null>(null);
  const [peers,setPeers]=useState<Ad[]>([]);
  const [baseline,setBaseline]=useState<number|null>(null);
  const [sigma,setSigma]=useState<number|null>(null);
  const [scanning,setScanning]=useState(false);
  const [calibrating,setCalibrating]=useState(false);
  const [xText,setXText]=useState('0');
  const [yText,setYText]=useState('0');
  const [x,setX]=useState<number|null>(0);
  const [y,setY]=useState<number|null>(0);
  const [error,setError]=useState<string|null>(null);
  const [nodeId]=useState(`android-${Math.random().toString(16).slice(2,10)}`);
  const tx=T[lang];

  useEffect(()=>{
    let live=true;
    (async()=>{
      try {
        await requestAndroidPermissions();
        setCaps(JSON.parse(BodyFinderNative.getCapabilitiesJson()));
        await BodyFinderNative.startFabric(nodeId,`${Platform.OS}-${nodeId.slice(-4)}`,'body-finder-lab');
      } catch(e:any) { if(live) setError(String(e?.message??e)); }
    })();
    const timer=setInterval(()=>{
      if(!live) return;
      try {
        setLocal(JSON.parse(BodyFinderNative.getLocalAdvertisementJson()) as Ad);
        setPeers(JSON.parse(BodyFinderNative.getPeersJson()) as Ad[]);
      } catch(e:any){ setError(String(e?.message??e)); }
    },1000);
    return()=>{live=false;clearInterval(timer);try{BodyFinderNative.stopFabric();}catch{}};
  },[nodeId]);

  useEffect(()=>{try{BodyFinderNative.updateLocalState(baseline,sigma,x,y,scanning);}catch{}},[baseline,sigma,x,y,scanning]);

  const nodes=useMemo(()=>local?[local,...peers]:peers,[local,peers]);
  const arrayTarget=useMemo(()=>estimateArray(nodes),[nodes]);
  const target=useMemo(()=>relativeToLocal(arrayTarget,local?.position),[arrayTarget,local?.position]);
  const coordinator=useMemo(()=>nodes.slice().sort((a,b)=>b.coordinator_score-a.coordinator_score||a.node_id.localeCompare(b.node_id))[0]?.node_id??null,[nodes]);
  const localPos=local?.position??{x_m:x??0,y_m:y??0};

  async function calibrate(){
    setCalibrating(true);setScanning(false);setError(null);
    const samples:number[]=[];
    try {
      for(let i=0;i<32;i++){const r=BodyFinderNative.getWifiRssi();if(typeof r==='number')samples.push(r);await sleep(250);}
      if(samples.length<8)throw new Error('Not enough live Wi-Fi RSSI samples. Connect to Wi-Fi and allow Nearby/Location access.');
      const mean=samples.reduce((a,b)=>a+b,0)/samples.length;
      const sd=Math.max(1,Math.sqrt(samples.reduce((a,b)=>a+(b-mean)**2,0)/samples.length));
      setBaseline(mean);setSigma(sd);
    }catch(e:any){setError(String(e?.message??e));}finally{setCalibrating(false);}
  }
  function savePos(){const nx=Number(xText),ny=Number(yText);if(Number.isFinite(nx)&&Number.isFinite(ny)){setX(nx);setY(ny);}}
  async function share(){
    const payload={report_version:2,generated_at:new Date().toISOString(),app:'Body Finder – RuView',build:'0.1.0-experimental.1',
      truth:'LIVE_DEVICE_CAPABILITIES_AND_RSSI__EXPERIMENTAL_LOCALIZATION_NOT_VALIDATED',node_id:nodeId,
      capabilities:caps,local,peers,coordinator_node_id:coordinator,estimate_array_frame:arrayTarget,
      estimate_relative_to_this_device:target,
      instructions:'Return this JSON plus Ubuntu/Windows JSONL logs and ground truth to ChatGPT for analysis.'};
    await Share.share({message:JSON.stringify(payload,null,2),title:'Body Finder field result'});
  }

  const scale=18;
  return <SafeAreaView style={s.safe}><StatusBar style="light"/>
    <View style={s.header}><View><Text style={s.title}>{tx.title}</Text><Text style={s.warn}>{tx.experimental}</Text></View><Pressable onPress={()=>setLang(lang==='en'?'es':'en')}><Text style={s.link}>{lang.toUpperCase()}</Text></Pressable></View>
    <View style={s.tabs}><Pressable style={[s.tab,mode==='radar'&&s.tabOn]} onPress={()=>setMode('radar')}><Text style={s.tabText}>{tx.radar}</Text></Pressable><Pressable style={[s.tab,mode==='expert'&&s.tabOn]} onPress={()=>setMode('expert')}><Text style={s.tabText}>{tx.expert}</Text></Pressable></View>
    {mode==='radar'?<ScrollView contentContainerStyle={s.body}>
      <View style={s.statusRow}><Text style={s.pill}>{nodes.length} {tx.peers}</Text><Text style={s.pill}>COORD {coordinator?.slice(-8)??'—'}</Text></View>
      <Text style={s.network}>{tx.network}</Text>
      <Text style={s.relative}>{tx.relative}</Text>
      <View style={s.radar}>
        {[90,180,270].map(d=><View key={d} style={[s.ring,{width:d,height:d,borderRadius:d/2,left:150-d/2,top:150-d/2}]}/>) }
        <View style={s.operator}/>
        {nodes.filter(n=>n.position).map((n,i)=>{const dx=n.position!.x_m-localPos.x_m,dy=n.position!.y_m-localPos.y_m;return <View key={n.node_id} style={[s.sensor,{left:144+dx*scale,top:144-dy*scale}]}><Text style={s.dotLabel}>{i+1}</Text></View>;})}
        {target&&<><View style={[s.targetRing,{width:Math.min(260,target.error_radius_95_m*36),height:Math.min(260,target.error_radius_95_m*36),borderRadius:130,left:150-Math.min(260,target.error_radius_95_m*36)/2+target.x_m*scale,top:150-Math.min(260,target.error_radius_95_m*36)/2-target.y_m*scale}]}/><View style={[s.target,{left:144+target.x_m*scale,top:144-target.y_m*scale}]}/></>}
      </View>
      {target?<View style={s.card}><Text style={s.h2}>{target.state.replace('_',' ')}</Text><Text style={s.big}>{target.range_m.toFixed(1)} m · {target.bearing_deg.toFixed(0)}°</Text><Text style={s.text}>x {target.x_m.toFixed(2)} m · y {target.y_m.toFixed(2)} m</Text><Text style={s.text}>{tx.confidence}: {(target.human_confidence*100).toFixed(0)}%</Text><Text style={s.text}>{tx.uncertainty}: {target.uncertainty_percent.toFixed(0)}% · ±{target.error_radius_95_m.toFixed(1)} m (95%)</Text><Text style={s.text}>quality: {target.quality}</Text><Text style={s.muted}>{tx.evidence}</Text></View>:<View style={s.card}><Text style={s.text}>{tx.noTarget}</Text></View>}
      <View style={s.card}><Text style={s.h2}>{tx.pos}</Text><View style={s.inputRow}><TextInput value={xText} onChangeText={setXText} keyboardType="numbers-and-punctuation" style={s.input} placeholder="x" placeholderTextColor="#777"/><TextInput value={yText} onChangeText={setYText} keyboardType="numbers-and-punctuation" style={s.input} placeholder="y" placeholderTextColor="#777"/><Pressable style={s.smallBtn} onPress={savePos}><Text style={s.btnText}>{tx.set}</Text></Pressable></View><Text style={s.muted}>Current array coordinate: ({x?.toFixed(1)??'?'}, {y?.toFixed(1)??'?'}) m. Measure it; do not invent coordinates.</Text></View>
      <Text style={s.muted}>{tx.empty}</Text>
      <Pressable disabled={calibrating} style={s.btn} onPress={calibrate}><Text style={s.btnText}>{calibrating?'CALIBRATING…':tx.calibrate}</Text></Pressable>
      <Pressable disabled={baseline==null} style={[s.btn,baseline==null&&s.disabled]} onPress={()=>setScanning(v=>!v)}><Text style={s.btnText}>{scanning?tx.stop:tx.scanning}</Text></Pressable>
      <Pressable style={s.btnAlt} onPress={share}><Text style={s.btnText}>{tx.share}</Text></Pressable>
      {error&&<Text style={s.err}>{error}</Text>}
    </ScrollView>:<ScrollView contentContainerStyle={s.body}>
      <View style={s.card}><Text style={s.h2}>Truth / source classification</Text><Text style={s.text}>RSSI: LIVE OS measurement when available</Text><Text style={s.text}>CSI: UNSUPPORTED unless a future verified adapter is loaded</Text><Text style={s.text}>Localization: EXPERIMENTAL / requires ground-truth validation</Text></View>
      <View style={s.card}><Text style={s.h2}>Capabilities</Text><Text selectable style={s.code}>{JSON.stringify(caps,null,2)}</Text></View>
      <View style={s.card}><Text style={s.h2}>Local node</Text><Text selectable style={s.code}>{JSON.stringify(local,null,2)}</Text></View>
      <View style={s.card}><Text style={s.h2}>Peers</Text><Text selectable style={s.code}>{JSON.stringify(peers,null,2)}</Text></View>
      <View style={s.card}><Text style={s.h2}>Array-frame estimate</Text><Text selectable style={s.code}>{JSON.stringify(arrayTarget,null,2)}</Text></View>
      <View style={s.card}><Text style={s.h2}>Relative estimate</Text><Text selectable style={s.code}>{JSON.stringify(target,null,2)}</Text></View>
    </ScrollView>}
  </SafeAreaView>;
}

const s=StyleSheet.create({
  safe:{flex:1,backgroundColor:'#071015'},header:{padding:14,flexDirection:'row',justifyContent:'space-between',alignItems:'center',borderBottomWidth:1,borderBottomColor:'#22313a'},title:{color:'#eefcff',fontSize:21,fontWeight:'800'},warn:{color:'#ffb454',fontSize:9,maxWidth:300,marginTop:2},link:{color:'#52d9e8',fontWeight:'800'},tabs:{flexDirection:'row',padding:8,gap:8},tab:{flex:1,padding:10,borderRadius:9,backgroundColor:'#111d24',alignItems:'center'},tabOn:{backgroundColor:'#17404a'},tabText:{color:'#e7fbff',fontWeight:'700'},body:{padding:14,gap:10},statusRow:{flexDirection:'row',gap:8},pill:{color:'#8deaf4',backgroundColor:'#102a31',paddingHorizontal:10,paddingVertical:5,borderRadius:14,fontSize:11},network:{color:'#ff8f8f',fontSize:10,fontWeight:'700'},relative:{color:'#8deaf4',fontSize:10,fontWeight:'800',textAlign:'center'},radar:{width:300,height:300,alignSelf:'center',borderRadius:150,borderWidth:1,borderColor:'#32535c',backgroundColor:'#09171c',overflow:'hidden'},ring:{position:'absolute',borderWidth:1,borderColor:'#1b3841'},operator:{position:'absolute',left:145,top:145,width:10,height:10,backgroundColor:'#fff',transform:[{rotate:'45deg'}]},sensor:{position:'absolute',width:12,height:12,borderRadius:6,backgroundColor:'#52d9e8',alignItems:'center',justifyContent:'center'},dotLabel:{fontSize:7,color:'#001014',fontWeight:'900'},target:{position:'absolute',width:12,height:12,borderRadius:6,backgroundColor:'#ffcf56'},targetRing:{position:'absolute',borderWidth:2,borderColor:'#ffcf56aa',backgroundColor:'#ffcf5618'},card:{backgroundColor:'#0d1b21',padding:13,borderRadius:12,borderWidth:1,borderColor:'#19313a'},h2:{color:'#8deaf4',fontSize:13,fontWeight:'800',marginBottom:5},big:{color:'#fff',fontSize:25,fontWeight:'800'},text:{color:'#e6f2f5',fontSize:13,marginVertical:2},muted:{color:'#87a2aa',fontSize:11},code:{color:'#b7d5dc',fontFamily:Platform.select({android:'monospace',default:'Courier'}),fontSize:10},inputRow:{flexDirection:'row',gap:7,alignItems:'center'},input:{flex:1,color:'#fff',backgroundColor:'#071015',padding:9,borderRadius:7,borderWidth:1,borderColor:'#29414a'},btn:{backgroundColor:'#1e7080',padding:13,borderRadius:10,alignItems:'center'},btnAlt:{backgroundColor:'#38454b',padding:13,borderRadius:10,alignItems:'center'},smallBtn:{backgroundColor:'#1e7080',padding:10,borderRadius:8},btnText:{color:'#fff',fontWeight:'800',fontSize:12},disabled:{opacity:.35},err:{color:'#ff7b7b'}
});
