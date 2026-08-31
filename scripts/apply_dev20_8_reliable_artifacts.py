#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
KT=ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
HP=ROOT/'apps/mobile/src/humanPresence.ts'
WIRE_SCHEMA=ROOT/'validation/schemas/wire-envelope-v8-schema.json'
TEST=ROOT/'validation/analysis/test_dev20_8_contract.py'

kt=KT.read_text(encoding='utf-8')
wire=r'''private object WireTransportV8 {
  const val MAX_DATAGRAM_BYTES = 1200
  private const val CHUNK_BYTES = 512
  private const val ASSEMBLY_TIMEOUT_MS = 15_000L
  private const val NACK_INTERVAL_MS = 500L
  private const val FULL_RETRY_MS = 3_000L
  private const val MAX_ASSEMBLIES = 16
  private const val MAX_ARTIFACT_CACHE = 32
  private const val MAX_OUTBOUND = 16
  private const val EXPECTED_REMOTE_ACKS = 2

  private data class Assembly(
    val artifactId:String, val artifactType:String, val sha:String, val count:Int, val generation:Long,
    val created:Long, val source:InetAddress, var lastNackWallMs:Long=0L,
    val chunks:java.util.concurrent.ConcurrentHashMap<Int,ByteArray> = java.util.concurrent.ConcurrentHashMap()
  )
  private data class CachedArtifact(val sha:String,val payload:JSONObject,val completedWallMs:Long)
  private data class OutboundArtifact(
    val artifactId:String,val artifactType:String,val sha:String,val generation:Long,val node:String,val session:String,
    val chunks:List<ByteArray>,var seq:Long,var lastFullSendWallMs:Long=0L,
    val ackPeers:MutableSet<String> = java.util.concurrent.ConcurrentHashMap.newKeySet()
  )
  data class WireReply(val address:InetAddress,val frame:ByteArray)
  data class ConsumeResult(val document:JSONObject?,val replies:List<WireReply>)

  private val assemblies=java.util.concurrent.ConcurrentHashMap<String,Assembly>()
  private val peerDocs=java.util.concurrent.ConcurrentHashMap<String,JSONObject>()
  private val lastAppliedSeq=java.util.concurrent.ConcurrentHashMap<String,Long>()
  private val artifactCache=java.util.LinkedHashMap<String,CachedArtifact>(MAX_ARTIFACT_CACHE,0.75f,true)
  private val outbound=java.util.LinkedHashMap<String,OutboundArtifact>(MAX_OUTBOUND,0.75f,true)
  private val txFramesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val rxFramesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val txBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()
  private val rxBytesByType=java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>()

  val oversizeBlockCount=java.util.concurrent.atomic.AtomicLong(0)
  val sendErrorCount=java.util.concurrent.atomic.AtomicLong(0)
  val maxDatagramBytesObserved=java.util.concurrent.atomic.AtomicLong(0)
  val txFrames=java.util.concurrent.atomic.AtomicLong(0)
  val rxFrames=java.util.concurrent.atomic.AtomicLong(0)
  val artifactStarted=java.util.concurrent.atomic.AtomicLong(0)
  val artifactCompleted=java.util.concurrent.atomic.AtomicLong(0)
  val artifactFailed=java.util.concurrent.atomic.AtomicLong(0)
  val artifactAckTx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactAckRx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactNackTx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactNackRx=java.util.concurrent.atomic.AtomicLong(0)
  val artifactRetransmitChunks=java.util.concurrent.atomic.AtomicLong(0)
  val artifactDedupChunks=java.util.concurrent.atomic.AtomicLong(0)
  val artifactCacheHits=java.util.concurrent.atomic.AtomicLong(0)
  val artifactCacheEvictions=java.util.concurrent.atomic.AtomicLong(0)
  val artifactOutboundEvictions=java.util.concurrent.atomic.AtomicLong(0)
  val artifactReassemblyTimeouts=java.util.concurrent.atomic.AtomicLong(0)
  val unknownFrameCount=java.util.concurrent.atomic.AtomicLong(0)
  val receiveErrorCount=java.util.concurrent.atomic.AtomicLong(0)
  @Volatile var lastSendError:String?=null
  @Volatile var lastReceiveError:String?=null

  private fun sha(bytes:ByteArray)=java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString(""){"%02x".format(it)}
  private fun crc32(bytes:ByteArray):Long=java.util.zip.CRC32().also{it.update(bytes)}.value
  private fun canonical(v:Any?):String=when(v){
    null,JSONObject.NULL->"null"
    is JSONObject->v.keys().asSequence().toList().sorted().joinToString(prefix="{",postfix="}"){k->JSONObject.quote(k)+":"+canonical(v.opt(k))}
    is JSONArray->(0 until v.length()).joinToString(prefix="[",postfix="]"){i->canonical(v.opt(i))}
    is String->JSONObject.quote(v)
    is Boolean,is Number->v.toString()
    else->JSONObject.quote(v.toString())
  }
  private fun mapJson(m:java.util.concurrent.ConcurrentHashMap<String,java.util.concurrent.atomic.AtomicLong>):JSONObject {
    val o=JSONObject();m.keys.sorted().forEach{k->o.put(k,m[k]?.get()?:0L)};return o
  }
  private fun envelope(type:String,node:String,session:String,seq:Long,body:(JSONObject)->Unit):ByteArray {
    val o=JSONObject().put("schema","WireEnvelopeV8").put("message_type",type).put("session_id",session).put("node_id",node).put("seq",seq)
    body(o)
    var b=o.toString().toByteArray(Charsets.UTF_8)
    o.put("wire_payload_bytes",b.size)
    b=o.toString().toByteArray(Charsets.UTF_8)
    o.put("wire_payload_bytes",b.size)
    b=o.toString().toByteArray(Charsets.UTF_8)
    maxDatagramBytesObserved.updateAndGet{v->kotlin.math.max(v,b.size.toLong())}
    if(b.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();throw IllegalStateException("WIRE_OVERSIZE_${type}_${b.size}")}
    return b
  }
  private fun safeAdd(out:MutableList<ByteArray>,type:String,node:String,session:String,seq:Long,body:(JSONObject)->Unit){
    try{out+=envelope(type,node,session,seq,body)}catch(t:Throwable){lastSendError="${t.javaClass.simpleName}:${t.message}"}
  }
  @Synchronized private fun putArtifactCache(id:String,value:CachedArtifact){
    artifactCache[id]=value
    while(artifactCache.size>MAX_ARTIFACT_CACHE){val it=artifactCache.entries.iterator();if(it.hasNext()){it.next();it.remove();artifactCacheEvictions.incrementAndGet()}else break}
  }
  @Synchronized private fun cachedArtifact(id:String):CachedArtifact?=artifactCache[id]
  @Synchronized private fun putOutbound(value:OutboundArtifact){
    outbound[value.artifactId]=value
    while(outbound.size>MAX_OUTBOUND){val it=outbound.entries.iterator();if(it.hasNext()){it.next();it.remove();artifactOutboundEvictions.incrementAndGet()}else break}
  }
  @Synchronized private fun outboundArtifact(id:String):OutboundArtifact?=outbound[id]
  private fun doc(node:String,session:String):JSONObject=peerDocs.computeIfAbsent(node){JSONObject().put("protocol_version",2).put("session_id",session).put("node_id",node).put("ranges",JSONArray()).put("control_plane",JSONObject()).put("artifact_cache_v1",JSONObject())}
  private fun applyDedup(o:JSONObject,subkey:String=""):Boolean{
    val type=o.optString("message_type");if(type.startsWith("ARTIFACT_"))return true
    val key="${o.optString("node_id")}|$type|$subkey";val seq=o.optLong("seq",0L);val prior=lastAppliedSeq[key]
    if(prior!=null&&seq<=prior)return false;lastAppliedSeq[key]=seq;return true
  }
  private fun updateRange(d:JSONObject,r:JSONObject){
    val arr=d.optJSONArray("ranges")?:JSONArray();val key="${r.optString("observer_node_id")}::${r.optString("peer_node_id")}";val next=JSONArray();var replaced=false
    for(i in 0 until arr.length()){val x=arr.optJSONObject(i)?:continue;val k="${x.optString("observer_node_id")}::${x.optString("peer_node_id")}";if(k==key){next.put(r);replaced=true}else next.put(x)}
    if(!replaced)next.put(r);d.put("ranges",next)
  }
  private fun updateGeometryPosition(d:JSONObject,p:JSONObject){
    val g=d.optJSONObject("published_geometry")?:JSONObject().put("positions",JSONArray());val arr=g.optJSONArray("positions")?:JSONArray();val id=p.optString("node_id");val next=JSONArray();var replaced=false
    for(i in 0 until arr.length()){val x=arr.optJSONObject(i)?:continue;if(x.optString("node_id")==id){next.put(p);replaced=true}else next.put(x)}
    if(!replaced)next.put(p);g.put("positions",next);d.put("published_geometry",g)
  }
  private fun registerArtifact(item:JSONObject,node:String,session:String,seq:Long):OutboundArtifact?{
    val id=item.optString("artifact_id");val type=item.optString("artifact_type");val payload=item.opt("payload")
    if(id.isBlank()||type.isBlank()||payload==null||payload===JSONObject.NULL)return null
    val bytes=canonical(payload).toByteArray(Charsets.UTF_8);val digest=sha(bytes);val chunks=bytes.toList().chunked(CHUNK_BYTES).map{it.toByteArray()};if(chunks.isEmpty())return null
    val existing=outboundArtifact(id);if(existing!=null&&existing.sha==digest){existing.seq=seq;return existing}
    return OutboundArtifact(id,type,digest,item.optLong("generation",0L),node,session,chunks,seq).also{putOutbound(it)}
  }
  private fun manifestFrame(a:OutboundArtifact)=envelope("ARTIFACT_MANIFEST",a.node,a.session,a.seq){it.put("artifact_id",a.artifactId).put("artifact_type",a.artifactType).put("artifact_sha256",a.sha).put("artifact_size",a.chunks.sumOf{x->x.size}).put("chunk_count",a.chunks.size).put("generation",a.generation)}
  private fun chunkFrame(a:OutboundArtifact,index:Int,seq:Long=a.seq)=envelope("ARTIFACT_CHUNK",a.node,a.session,seq){val c=a.chunks[index];it.put("artifact_id",a.artifactId).put("artifact_sha256",a.sha).put("chunk_index",index).put("chunk_count",a.chunks.size).put("payload_crc32",crc32(c)).put("payload_b64",android.util.Base64.encodeToString(c,android.util.Base64.NO_WRAP))}
  private fun ackFrame(id:String,digest:String,seq:Long)=envelope("ARTIFACT_ACK",FabricRuntime.nodeId,FabricRuntime.sessionId,seq){it.put("artifact_id",id).put("artifact_sha256",digest).put("complete",true)}
  private fun nackFrame(id:String,digest:String,missing:List<Int>,seq:Long)=envelope("ARTIFACT_NACK",FabricRuntime.nodeId,FabricRuntime.sessionId,seq){it.put("artifact_id",id).put("artifact_sha256",digest).put("missing_chunks",JSONArray(missing.take(64)))}

  fun frames(advertisement:JSONObject,node:String,session:String,seq:Long):List<ByteArray>{
    val out=mutableListOf<ByteArray>()
    safeAdd(out,"HEARTBEAT",node,session,seq){o->
      for(k in listOf("protocol_version","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(advertisement.has(k))o.put(k,advertisement.opt(k))
    }
    val ranges=advertisement.optJSONArray("ranges")?:JSONArray()
    for(i in 0 until ranges.length()){val r=ranges.optJSONObject(i)?:continue;val sub="${r.optString("observer_node_id")}::${r.optString("peer_node_id")}";safeAdd(out,"RANGE_FRAME",node,session,seq){o->o.put("range_key",sub).put("range",r)}}
    val cp=advertisement.optJSONObject("control_plane")
    val artifacts=mutableMapOf<String,OutboundArtifact>()
    if(cp!=null){
      val payloads=cp.optJSONArray("artifact_payloads_v1")?:JSONArray()
      for(i in 0 until payloads.length()){val item=payloads.optJSONObject(i)?:continue;registerArtifact(item,node,session,seq)?.let{artifacts[it.artifactId]=it}}
      val meta=JSONObject();for(k in listOf("schema","session_id","node_id"))if(cp.has(k))meta.put(k,cp.opt(k));safeAdd(out,"CONTROL_FRAME",node,session,seq){o->o.put("control_key","__meta__").put("control_value",meta)}
      for(k in listOf("logical_membership_state","calibration_publication_v8","calibration_ack_v8","decision_publication_v8","decision_ack_v8")){
        if(!cp.has(k)||cp.isNull(k))continue;val value=cp.opt(k);val copy=if(value is JSONObject)JSONObject(value.toString())else value
        if(copy is JSONObject){val id=copy.optString("calibration_artifact_id").ifBlank{copy.optString("decision_artifact_id")};artifacts[id]?.let{copy.put("artifact_sha256",it.sha)}}
        safeAdd(out,"CONTROL_FRAME",node,session,seq){o->o.put("control_key",k).put("control_value",copy)}
      }
      val now=System.currentTimeMillis()
      for(a in artifacts.values){
        try{out+=manifestFrame(a)}catch(t:Throwable){lastSendError="${t.javaClass.simpleName}:${t.message}"}
        if(a.ackPeers.size<EXPECTED_REMOTE_ACKS&&now-a.lastFullSendWallMs>=FULL_RETRY_MS){for(i in a.chunks.indices)try{out+=chunkFrame(a,i)}catch(t:Throwable){lastSendError="${t.javaClass.simpleName}:${t.message}"};a.lastFullSendWallMs=now}
      }
    }
    val g=advertisement.optJSONObject("published_geometry")
    if(g!=null){
      val meta=JSONObject();for(k in listOf("frame_id","revision","generated_monotonic_ns","dimension","state","anchor_node_id","axis_node_id","residual_rms_m","condition_score","reason"))if(g.has(k))meta.put(k,g.opt(k));safeAdd(out,"GEOMETRY_FRAME",node,session,seq){o->o.put("geometry",meta)}
      val positions=g.optJSONArray("positions")?:JSONArray();for(i in 0 until positions.length()){val p=positions.optJSONObject(i)?:continue;safeAdd(out,"GEOMETRY_POSITION_FRAME",node,session,seq){o->o.put("position",p)}}
    }
    return out
  }
  private fun frameType(frame:ByteArray):String=try{JSONObject(String(frame,Charsets.UTF_8)).optString("message_type","UNKNOWN")}catch(_:Throwable){"UNKNOWN"}
  fun send(socket:MulticastSocket,address:InetAddress,port:Int,frames:List<ByteArray>){
    for(frame in frames){
      if(frame.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();continue};val type=frameType(frame)
      try{socket.send(DatagramPacket(frame,frame.size,address,port));txFrames.incrementAndGet();FabricRuntime.txPackets.incrementAndGet();txFramesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.incrementAndGet();txBytesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.addAndGet(frame.size.toLong())}catch(t:Throwable){sendErrorCount.incrementAndGet();lastSendError="${t.javaClass.simpleName}:${t.message}"}
    }
  }
  private fun missing(a:Assembly)= (0 until a.count).filter{!a.chunks.containsKey(it)}
  private fun reply(address:InetAddress,frame:ByteArray)=WireReply(address,frame)
  private fun artifactDoc(node:String,session:String,id:String,payload:JSONObject,sha:String):JSONObject{
    val d=doc(node,session);val cache=d.optJSONObject("artifact_cache_v1")?:JSONObject();cache.put(id,payload);d.put("artifact_cache_v1",cache);val meta=d.optJSONObject("artifact_cache_meta_v1")?:JSONObject();meta.put(id,JSONObject().put("artifact_sha256",sha).put("complete",true));d.put("artifact_cache_meta_v1",meta);return d
  }
  fun consume(text:String,source:InetAddress):ConsumeResult{
    val o=try{JSONObject(text)}catch(t:Throwable){receiveErrorCount.incrementAndGet();lastReceiveError="${t.javaClass.simpleName}:${t.message}";return ConsumeResult(null,emptyList())}
    if(o.optString("schema")!="WireEnvelopeV8")return ConsumeResult(o,emptyList())
    val bytes=text.toByteArray(Charsets.UTF_8);val type=o.optString("message_type");rxFrames.incrementAndGet();rxFramesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.incrementAndGet();rxBytesByType.computeIfAbsent(type){java.util.concurrent.atomic.AtomicLong(0)}.addAndGet(bytes.size.toLong());maxDatagramBytesObserved.updateAndGet{v->kotlin.math.max(v,bytes.size.toLong())}
    if(bytes.size>MAX_DATAGRAM_BYTES){oversizeBlockCount.incrementAndGet();return ConsumeResult(null,emptyList())}
    val session=o.optString("session_id");if(session!=FabricRuntime.sessionId)return ConsumeResult(null,emptyList());val node=o.optString("node_id");if(node.isBlank()||node==FabricRuntime.nodeId)return ConsumeResult(null,emptyList());val seq=o.optLong("seq",0L);val now=System.currentTimeMillis();val replies=mutableListOf<WireReply>()
    when(type){
      "HEARTBEAT"->{if(!applyDedup(o))return ConsumeResult(null,emptyList());val d=doc(node,session);for(k in listOf("protocol_version","display_name","platform","coordinator_score","rssi_dbm","baseline_rssi_dbm","baseline_sigma_db","scanning","ble_identity","manual_geometry_override"))if(o.has(k))d.put(k,o.opt(k));return ConsumeResult(d,replies)}
      "RANGE_FRAME"->{val key=o.optString("range_key");if(!applyDedup(o,key))return ConsumeResult(null,emptyList());val r=o.optJSONObject("range")?:return ConsumeResult(null,emptyList());val d=doc(node,session);updateRange(d,r);return ConsumeResult(d,replies)}
      "CONTROL_FRAME"->{val key=o.optString("control_key");if(!applyDedup(o,key))return ConsumeResult(null,emptyList());val d=doc(node,session);val cp=d.optJSONObject("control_plane")?:JSONObject();val value=o.opt("control_value");if(key=="__meta__"&&value is JSONObject){value.keys().forEach{k->cp.put(k,value.opt(k))}}else cp.put(key,value);d.put("control_plane",cp);return ConsumeResult(d,replies)}
      "GEOMETRY_FRAME"->{if(!applyDedup(o,"meta"))return ConsumeResult(null,emptyList());val d=doc(node,session);val g=o.optJSONObject("geometry")?:JSONObject();val existing=d.optJSONObject("published_geometry");if(existing!=null&&existing.has("positions"))g.put("positions",existing.optJSONArray("positions"));d.put("published_geometry",g);return ConsumeResult(d,replies)}
      "GEOMETRY_POSITION_FRAME"->{val p=o.optJSONObject("position")?:return ConsumeResult(null,emptyList());if(!applyDedup(o,p.optString("node_id")))return ConsumeResult(null,emptyList());val d=doc(node,session);updateGeometryPosition(d,p);return ConsumeResult(d,replies)}
      "ARTIFACT_MANIFEST"->{val id=o.optString("artifact_id");val digest=o.optString("artifact_sha256");val count=o.optInt("chunk_count");if(id.isBlank()||digest.isBlank()||count<=0||count>4096)return ConsumeResult(null,emptyList());val cached=cachedArtifact(id);if(cached!=null&&cached.sha==digest){artifactCacheHits.incrementAndGet();artifactAckTx.incrementAndGet();replies+=reply(source,ackFrame(id,digest,now));return ConsumeResult(artifactDoc(node,session,id,cached.payload,digest),replies)};assemblies.computeIfAbsent(id){artifactStarted.incrementAndGet();Assembly(id,o.optString("artifact_type"),digest,count,o.optLong("generation",0L),now,source)};return ConsumeResult(null,replies)}
      "ARTIFACT_CHUNK"->{val id=o.optString("artifact_id");val digest=o.optString("artifact_sha256");val count=o.optInt("chunk_count");val idx=o.optInt("chunk_index",-1);if(id.isBlank()||digest.isBlank()||idx !in 0 until count)return ConsumeResult(null,emptyList());val a=assemblies.computeIfAbsent(id){artifactStarted.incrementAndGet();Assembly(id,"UNKNOWN",digest,count,0L,now,source)};if(a.sha!=digest||a.count!=count){artifactFailed.incrementAndGet();return ConsumeResult(null,replies)};val chunk=try{android.util.Base64.decode(o.optString("payload_b64"),android.util.Base64.DEFAULT)}catch(_:Throwable){byteArrayOf()};if(chunk.size>CHUNK_BYTES||crc32(chunk)!=o.optLong("payload_crc32",-1L)){artifactFailed.incrementAndGet();artifactNackTx.incrementAndGet();replies+=reply(source,nackFrame(id,digest,listOf(idx),now));return ConsumeResult(null,replies)};if(a.chunks.putIfAbsent(idx,chunk)!=null)artifactDedupChunks.incrementAndGet();if(a.chunks.size==a.count){val payload=(0 until a.count).flatMap{(a.chunks[it]?:byteArrayOf()).toList()}.toByteArray();assemblies.remove(id);if(sha(payload)!=a.sha){artifactFailed.incrementAndGet();artifactNackTx.incrementAndGet();replies+=reply(source,nackFrame(id,digest,(0 until count).toList(),now));return ConsumeResult(null,replies)};val obj=try{JSONObject(String(payload,Charsets.UTF_8))}catch(_:Throwable){artifactFailed.incrementAndGet();return ConsumeResult(null,replies)};putArtifactCache(id,CachedArtifact(digest,obj,now));artifactCompleted.incrementAndGet();artifactAckTx.incrementAndGet();replies+=reply(source,ackFrame(id,digest,now));return ConsumeResult(artifactDoc(node,session,id,obj,digest),replies)};if(idx==count-1){val miss=missing(a);if(miss.isNotEmpty()){a.lastNackWallMs=now;artifactNackTx.incrementAndGet();replies+=reply(source,nackFrame(id,digest,miss,now))}};return ConsumeResult(null,replies)}
      "ARTIFACT_ACK"->{artifactAckRx.incrementAndGet();val id=o.optString("artifact_id");val a=outboundArtifact(id);if(a!=null&&a.sha==o.optString("artifact_sha256"))a.ackPeers.add(node);return ConsumeResult(null,replies)}
      "ARTIFACT_NACK"->{artifactNackRx.incrementAndGet();val id=o.optString("artifact_id");val a=outboundArtifact(id)?:return ConsumeResult(null,replies);if(a.sha!=o.optString("artifact_sha256"))return ConsumeResult(null,replies);val miss=o.optJSONArray("missing_chunks")?:JSONArray();for(i in 0 until miss.length()){val idx=miss.optInt(i,-1);if(idx in a.chunks.indices){artifactRetransmitChunks.incrementAndGet();replies+=reply(source,chunkFrame(a,idx,now))}};return ConsumeResult(null,replies)}
      else->{unknownFrameCount.incrementAndGet();return ConsumeResult(null,replies)}
    }
  }
  fun maintenance(now:Long):List<WireReply>{
    val replies=mutableListOf<WireReply>();val entries=assemblies.entries.toList().sortedBy{it.value.created}
    if(entries.size>MAX_ASSEMBLIES)for(e in entries.take(entries.size-MAX_ASSEMBLIES)){if(assemblies.remove(e.key)!=null){artifactFailed.incrementAndGet();artifactReassemblyTimeouts.incrementAndGet()}}
    for((id,a) in assemblies.entries){val age=now-a.created;if(age>ASSEMBLY_TIMEOUT_MS){if(assemblies.remove(id)!=null){artifactFailed.incrementAndGet();artifactReassemblyTimeouts.incrementAndGet()};continue};if(now-a.lastNackWallMs>=NACK_INTERVAL_MS&&age>=NACK_INTERVAL_MS){val miss=missing(a);if(miss.isNotEmpty()){a.lastNackWallMs=now;artifactNackTx.incrementAndGet();replies+=reply(a.source,nackFrame(id,a.sha,miss,now))}}}
    return replies
  }
  fun noteReceiveError(t:Throwable){receiveErrorCount.incrementAndGet();lastReceiveError="${t.javaClass.simpleName}:${t.message}"}
  fun telemetry()=JSONObject()
    .put("schema","WireTransportTelemetryV8").put("max_datagram_budget_bytes",MAX_DATAGRAM_BYTES).put("chunk_payload_bytes",CHUNK_BYTES)
    .put("max_datagram_bytes_observed",maxDatagramBytesObserved.get()).put("wire_oversize_block_count",oversizeBlockCount.get())
    .put("wire_send_error_count",sendErrorCount.get()).put("wire_last_send_error",lastSendError?:JSONObject.NULL).put("wire_receive_error_count",receiveErrorCount.get()).put("wire_last_receive_error",lastReceiveError?:JSONObject.NULL)
    .put("tx_frames",txFrames.get()).put("rx_frames",rxFrames.get()).put("tx_frames_by_type",mapJson(txFramesByType)).put("rx_frames_by_type",mapJson(rxFramesByType)).put("tx_bytes_by_type",mapJson(txBytesByType)).put("rx_bytes_by_type",mapJson(rxBytesByType))
    .put("artifact_transfer_started",artifactStarted.get()).put("artifact_transfer_completed",artifactCompleted.get()).put("artifact_transfer_failed",artifactFailed.get()).put("artifact_reassembly_pending",assemblies.size)
    .put("artifact_ack_tx",artifactAckTx.get()).put("artifact_ack_rx",artifactAckRx.get()).put("artifact_nack_tx",artifactNackTx.get()).put("artifact_nack_rx",artifactNackRx.get()).put("artifact_retransmit_chunks",artifactRetransmitChunks.get()).put("artifact_dedup_chunks",artifactDedupChunks.get())
    .put("artifact_cache_size",synchronized(this){artifactCache.size}).put("artifact_cache_hits",artifactCacheHits.get()).put("artifact_cache_evictions",artifactCacheEvictions.get()).put("artifact_outbound_cache_size",synchronized(this){outbound.size}).put("artifact_outbound_evictions",artifactOutboundEvictions.get()).put("artifact_reassembly_timeouts",artifactReassemblyTimeouts.get()).put("unknown_frame_count",unknownFrameCount.get())
}
'''
pat=r'private object WireTransportV8 \{.*?\n\}\n\nprivate object FabricRuntime \{'
if not re.search(pat,kt,flags=re.S): raise SystemExit('WireTransportV8 block not found')
kt=re.sub(pat,wire+'\nprivate object FabricRuntime {',kt,count=1,flags=re.S)
kt=kt.replace('.put("snapshot_schema_version", 5)','.put("snapshot_schema_version", 11)')
old_send='''          if (now >= nextSend) {
            val payload = advertisement(ctx).toString().toByteArray(Charsets.UTF_8)
            try {
              val frames = WireTransportV8.frames(payload, FabricRuntime.nodeId, FabricRuntime.sessionId, now)
              WireTransportV8.send(socket, groupAddress, PORT, frames)
              WireTransportV8.send(socket, broadcastAddress, PORT, frames)
            } catch (t: Throwable) {
              WireTransportV8.sendErrorCount.incrementAndGet()
              WireTransportV8.lastSendError = "${t.javaClass.simpleName}:${t.message}"
            }
            nextSend = now + 800L
          }'''
new_send='''          if (now >= nextSend) {
            val ad = advertisement(ctx)
            try {
              val frames = WireTransportV8.frames(ad, FabricRuntime.nodeId, FabricRuntime.sessionId, now)
              WireTransportV8.send(socket, groupAddress, PORT, frames)
              WireTransportV8.send(socket, broadcastAddress, PORT, frames)
            } catch (t: Throwable) {
              WireTransportV8.sendErrorCount.incrementAndGet()
              WireTransportV8.lastSendError = "${t.javaClass.simpleName}:${t.message}"
            }
            nextSend = now + 800L
          }'''
if old_send not in kt and new_send not in kt: raise SystemExit('network send block not found')
kt=kt.replace(old_send,new_send,1)
old_rx='''            val text = String(packet.data, packet.offset, packet.length, Charsets.UTF_8)
            val obj = WireTransportV8.consume(text) ?: continue'''
new_rx='''            val text = String(packet.data, packet.offset, packet.length, Charsets.UTF_8)
            val consumed = WireTransportV8.consume(text, packet.address)
            for (reply in consumed.replies) WireTransportV8.send(socket, reply.address, PORT, listOf(reply.frame))
            val obj = consumed.document ?: continue'''
if old_rx not in kt and new_rx not in kt: raise SystemExit('network receive block not found')
kt=kt.replace(old_rx,new_rx,1)
kt=kt.replace('''          } catch (_: java.net.SocketTimeoutException) {
          } catch (_: Throwable) {}
          expirePeers(ctx, now)''','''          } catch (_: java.net.SocketTimeoutException) {
          } catch (t: Throwable) { WireTransportV8.noteReceiveError(t) }
          for (reply in WireTransportV8.maintenance(now)) WireTransportV8.send(socket, reply.address, PORT, listOf(reply.frame))
          expirePeers(ctx, now)''',1)
KT.write_text(kt,encoding='utf-8')

hp=HP.read_text(encoding='utf-8')
hp=re.sub(r"function publicationFrom\(nodes:Advertisement\[],coordinatorNodeId:string\|null\)\{.*?\}\nfunction currentSession",'''function artifactFrom(node:Advertisement|undefined,id:string|null|undefined){if(!node||!id)return null;return (node as any)?.artifact_cache_v1?.[id]??null}
function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);return (coordinator?.control_plane as any)?.calibration_publication_v8??null}
function currentSession''',hp,count=1,flags=re.S)
hp=re.sub(r"function syncAuthoritativeCalibration\(nodes:Advertisement\[],coordinatorNodeId:string\|null,localNodeId:string\|null\)\{.*?\n\}\nfunction adoptCoordinatorIfNeeded",'''function syncAuthoritativeCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;if(!coordinatorNodeId||coordinatorNodeId===localNodeId)return;const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId),p=publicationFrom(nodes,coordinatorNodeId),now=Date.now();
  const artifact=p?.calibration_artifact_id?artifactFrom(coordinator,p.calibration_artifact_id):null;
  if(p?.schema==='CalibrationPublicationV8'&&p?.detector_parameter_hash===DETECTOR_PARAMETER_HASH&&artifact?.calibration_hash===p?.calibration_hash){
    const incomingCg=Number(p.coordinator_generation??0),incomingCal=Number(p.calibration_generation??0),incomingSeq=Number(p.publication_sequence??0);
    const sameOrNewer=incomingCg>cal.coordinatorGeneration||(incomingCg===cal.coordinatorGeneration&&incomingCal>=cal.generation);const ordered=incomingCg>cal.coordinatorGeneration||incomingSeq>=cal.publicationSequence;
    if(sameOrNewer&&ordered){cal={...cal,state:'READY',generation:incomingCal,coordinator:coordinatorNodeId,topology:String(p.topology_fingerprint),artifact,reason:'AUTHORITATIVE_CALIBRATION_ARTIFACT_V8_COMPLETE',expectedCohort:Array.isArray(p.expected_cohort)?p.expected_cohort.map(String).sort():cal.expectedCohort,publicationSequence:incomingSeq,lastAuthorityWallMs:now,coordinatorGeneration:incomingCg}}
  }else if(p?.schema==='CalibrationPublicationV8'&&!artifact&&!cal.artifact){cal={...cal,state:'WAIT_COORDINATOR',coordinator:coordinatorNodeId,reason:'CALIBRATION_ARTIFACT_V8_PENDING'}}
  else if(cal.artifact&&cal.lastAuthorityWallMs&&now-cal.lastAuthorityWallMs>DETECTOR_V8.authorityPublicationLeaseMs){cal={...cal,state:'STALE_AUTHORITY',reason:'AUTHORITY_PUBLICATION_LEASE_EXPIRED_CALIBRATION_PRESERVED'}}
}
function adoptCoordinatorIfNeeded''',hp,count=1,flags=re.S)
hp=re.sub(r"function exactAck\(node:Advertisement,id:string\)\{.*?\n\}",'''function exactAck(node:Advertisement,id:string){
  if(!cal.artifact)return false;if(id===cal.coordinator)return true;if(id===lastLocalNodeId&&cal.expectedCohort.includes(id))return true;
  const a=(node.control_plane as any)?.calibration_ack_v8;
  return Boolean(a&&a.schema==='CalibrationAckV8'&&a.node_id===id&&a.calibration_id===cal.artifact.calibration_id&&a.calibration_hash===cal.artifact.calibration_hash&&Number(a.calibration_generation)===cal.generation&&Number(a.coordinator_generation)===cal.coordinatorGeneration);
}''',hp,count=1,flags=re.S)
block=r"export function getCalibrationPublication\(localNodeId:string\|null\)\{.*?\n\}\nexport function getControlPlanePublication\(nodes:Advertisement\[],coordinatorNodeId:string\|null,localNodeId:string\|null\)\{.*?\n\}\n\nfunction maybeFreeze"
replacement='''export function getCalibrationPublication(localNodeId:string|null){
  if(!cal.artifact||cal.coordinator!==localNodeId||cal.state!=='READY')return null;cal.publicationSequence+=1;cal.lastAuthorityWallMs=Date.now();
  return{schema:'CalibrationPublicationV8',session_id:cal.artifact.session_id,coordinator_id:cal.coordinator,coordinator_generation:cal.coordinatorGeneration,calibration_generation:cal.generation,calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,calibration_artifact_id:`calibration:${cal.artifact.calibration_id}`,calibration_artifact_hash:cal.artifact.calibration_hash,topology_fingerprint:cal.topology,expected_cohort:cal.expectedCohort,publication_sequence:cal.publicationSequence,publication_wall_ms:Date.now(),lease_timeout_ms:DETECTOR_V8.authorityPublicationLeaseMs,detector_parameter_hash:DETECTOR_PARAMETER_HASH,state:'READY',reason:cal.reason}
}
export function getControlPlanePublication(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){
  lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes),calibrationPublication=getCalibrationPublication(localNodeId);
  const ack=cal.artifact&&localNodeId&&cal.expectedCohort.includes(localNodeId)?{schema:'CalibrationAckV8',session_id:cal.artifact.session_id,node_id:localNodeId,coordinator_id:cal.coordinator,coordinator_generation:cal.coordinatorGeneration,calibration_generation:cal.generation,calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,calibration_artifact_id:`calibration:${cal.artifact.calibration_id}`,ack_wall_ms:Date.now()}:null;
  const cached=latestDecisionBySession.get(sid);
  const decisionPublication=cached&&coordinatorNodeId===localNodeId&&cached.decision.authoritative&&cached.decision.canonical_digest?{schema:'DecisionPublicationV8',session_id:sid,coordinator_id:coordinatorNodeId,coordinator_generation:cal.coordinatorGeneration,calibration_id:cached.decision.calibration_id??cal.artifact?.calibration_id??null,calibration_hash:cached.decision.calibration_hash??cal.artifact?.calibration_hash??null,calibration_generation:cached.decision.calibration_generation??cal.generation,topology_fingerprint:cached.decision.topology_fingerprint??cal.topology,detector_algorithm:DETECTOR_ALGORITHM,detector_parameter_hash:DETECTOR_PARAMETER_HASH,decision_sequence:cached.sequence,decision_id:cached.decision.decision_id,canonical_digest:cached.decision.canonical_digest,window_id:cached.decision.window_id,publication_wall_ms:Date.now(),source_decision_wall_ms:cached.receivedWallMs,freshness_state:decisionFreshness(cached.receivedWallMs),fresh_ms:DECISION_FRESH_MS,expiry_ms:DECISION_EXPIRED_MS,prediction:cached.decision.prediction,fused_score:cached.decision.fused_score,evidence_quality:cached.decision.evidence_quality,contributing_nodes:cached.decision.contributing_nodes,contributing_links:cached.decision.contributing_links,physical_baselines:cached.decision.physical_baselines,decision_artifact_id:`decision:${cached.decision.decision_id}`,decision_artifact_hash:cached.decision.canonical_digest}:null;
  const decisionAck=cached&&localNodeId?{schema:'DecisionAckV8',session_id:sid,node_id:localNodeId,coordinator_id:coordinatorNodeId,coordinator_generation:cal.coordinatorGeneration,decision_sequence:cached.sequence,decision_id:cached.decision.decision_id??null,canonical_digest:cached.decision.canonical_digest??null,ack_wall_ms:Date.now()}:null;
  const artifacts:any[]=[];if(coordinatorNodeId===localNodeId&&calibrationPublication&&cal.artifact)artifacts.push({artifact_id:calibrationPublication.calibration_artifact_id,artifact_type:'CALIBRATION_ARTIFACT_V8',generation:cal.generation,payload:cal.artifact});if(coordinatorNodeId===localNodeId&&decisionPublication&&cached)artifacts.push({artifact_id:decisionPublication.decision_artifact_id,artifact_type:'DECISION_REPLAY_ARTIFACT_V8',generation:cached.sequence,payload:cached.decision});
  return{schema:'BodyFinderControlPlaneV8',session_id:sid,node_id:localNodeId,logical_membership_state:{expected_cohort:stableCohort(nodes),transport_liveness_state:transportStates(nodes)},calibration_publication_v8:calibrationPublication,calibration_ack_v8:ack,decision_publication_v8:decisionPublication,decision_ack_v8:decisionAck,artifact_payloads_v1:artifacts}
}

function maybeFreeze'''
if not re.search(block,hp,flags=re.S): raise SystemExit('publication block not found')
hp=re.sub(block,replacement,hp,count=1,flags=re.S)
hp=hp.replace('calibration_publication_v6:publication','calibration_publication_v8:publication')
start=hp.find('export function selectAuthoritativePresence(')
if start<0: raise SystemExit('selectAuthoritativePresence not found')
new_tail='''export function selectAuthoritativePresence(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,local:PresenceEstimate):PresenceEstimate{
  lastLocalNodeId=localNodeId;syncAuthoritativeCalibration(nodes,coordinatorNodeId,localNodeId);adoptCoordinatorIfNeeded(nodes,coordinatorNodeId,localNodeId);const sid=currentSession(nodes);
  if(!coordinatorNodeId)return fallback('coordinator_unavailable',cal.state,{transport_liveness_state:transportStates(nodes)});if(coordinatorNodeId===localNodeId)return local;
  const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const dp=(coordinator?.control_plane as any)?.decision_publication_v8;
  if(dp&&dp.schema==='DecisionPublicationV8'&&dp.session_id===sid&&dp.coordinator_id===coordinatorNodeId&&Number(dp.coordinator_generation)===cal.coordinatorGeneration&&dp.detector_algorithm===DETECTOR_ALGORITHM&&dp.detector_parameter_hash===DETECTOR_PARAMETER_HASH&&dp.calibration_hash===cal.artifact?.calibration_hash&&dp.canonical_digest){
    const artifact=artifactFrom(coordinator,dp.decision_artifact_id),incomingSeq=Number(dp.decision_sequence??0),previous=latestDecisionBySession.get(sid);
    if(artifact&&artifact.canonical_digest===dp.canonical_digest&&artifact.decision_id===dp.decision_id&&(!previous||incomingSeq>=previous.sequence)){const mirrored={...artifact,calibration_state:cal.artifact?'READY':artifact.calibration_state,source:'decision_control_plane_v8_artifact_complete',decision_sequence:incomingSeq,decision_freshness_state:'FRESH'} as PresenceEstimate;latestDecisionBySession.set(sid,{decision:mirrored,receivedWallMs:Date.now(),sequence:incomingSeq});return mirrored}
    if(!artifact)return{...fallback('DECISION_ARTIFACT_V8_PENDING',cal.state,{transport_liveness_state:transportStates(nodes)}),prediction:dp.prediction??'INDETERMINATE',fused_score:Number(dp.fused_score??0),evidence_quality:String(dp.evidence_quality??'LOW'),contributing_nodes:Number(dp.contributing_nodes??0),contributing_links:Number(dp.contributing_links??0),physical_baselines:Number(dp.physical_baselines??0),decision_id:dp.decision_id,canonical_digest:dp.canonical_digest,window_id:dp.window_id,source:'decision_control_plane_v8_compact_pending_artifact',authoritative:false}
  }
  const cached=latestDecisionBySession.get(sid);if(cached&&decisionFreshness(cached.receivedWallMs)!=='EXPIRED')return{...cached.decision,source:'cached_decision_publication_v8',decision_freshness_state:decisionFreshness(cached.receivedWallMs),decision_age_ms:Date.now()-cached.receivedWallMs} as PresenceEstimate;
  return fallback(cal.state==='STALE_AUTHORITY'?cal.reason:'WAIT_DECISION_EXPIRED',cal.state,{decision_freshness_state:cached?'EXPIRED':'WAIT_DECISION',last_valid_decision_sequence:cached?.sequence??null,last_valid_decision_digest:cached?.decision.canonical_digest??null,transport_liveness_state:transportStates(nodes)})
}
'''
hp=hp[:start]+new_tail
HP.write_text(hp,encoding='utf-8')

import json
schema=json.loads(WIRE_SCHEMA.read_text())
schema['properties']['message_type']['enum']=['HEARTBEAT','RANGE_FRAME','CONTROL_FRAME','GEOMETRY_FRAME','GEOMETRY_POSITION_FRAME','ARTIFACT_MANIFEST','ARTIFACT_CHUNK','ARTIFACT_ACK','ARTIFACT_NACK']
WIRE_SCHEMA.write_text(json.dumps(schema,indent=2,sort_keys=True)+'\n')

t=TEST.read_text(encoding='utf-8')
extra="""
assert 'ARTIFACT_ACK' in kt and 'ARTIFACT_NACK' in kt and 'artifactRetransmitChunks' in kt and 'artifactCacheEvictions' in kt
assert 'RANGE_FRAME' in kt and 'CONTROL_FRAME' in kt and 'GEOMETRY_FRAME' in kt
assert 'REDUNDANCY_ROUNDS' not in kt
assert "CalibrationPublicationV8" in hp and "CalibrationAckV8" in hp and 'artifact_payloads_v1' in hp
assert 'decision_artifact:cached.decision' not in hp and 'artifact:cal.artifact' not in hp
assert 'decision_control_plane_v8_artifact_complete' in hp and 'CALIBRATION_ARTIFACT_V8_PENDING' in hp
"""
if "assert 'ARTIFACT_ACK' in kt" not in t:t=t.replace("print('dev20.8 contract tests PASS')",extra+"\nprint('dev20.8 contract tests PASS')")
TEST.write_text(t,encoding='utf-8')
print('dev20.8 reliable typed wire/artifact plane applied')
