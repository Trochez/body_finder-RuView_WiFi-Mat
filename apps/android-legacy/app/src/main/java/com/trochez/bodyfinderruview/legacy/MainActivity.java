package com.trochez.bodyfinderruview.legacy;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONException;
import org.json.JSONObject;

import java.net.DatagramPacket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.MulticastSocket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final int PORT = 47777;
    private static final String GROUP = "239.255.77.77";
    private static final String SESSION = "body-finder-lab";
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Map<String, Long> peers = new HashMap<>();
    private volatile boolean running = true;
    private volatile boolean scanning = false;
    private volatile Double baseline = null;
    private volatile Double sigma = null;
    private volatile Double x = 0.0;
    private volatile Double y = 0.0;
    private String nodeId;
    private TextView status;
    private EditText xInput;
    private EditText yInput;
    private MulticastSocket socket;
    private WifiManager.MulticastLock multicastLock;

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        SharedPreferences sp = getSharedPreferences("bf", MODE_PRIVATE);
        nodeId = sp.getString("nodeId", null);
        if (nodeId == null) {
            nodeId = "legacy-" + UUID.randomUUID().toString().substring(0,8);
            sp.edit().putString("nodeId", nodeId).apply();
        }
        requestPermissionsIfNeeded();
        buildUi();
        startFabric();
    }

    private void requestPermissionsIfNeeded() {
        if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION}, 42);
        }
        if (Build.VERSION.SDK_INT >= 33) {
            try {
                String p = "android.permission.NEARBY_WIFI_DEVICES";
                if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{p},43);
            } catch (Throwable ignored) {}
        }
    }

    private TextView text(String value, int size) {
        TextView v = new TextView(this); v.setText(value); v.setTextColor(Color.rgb(225,245,248)); v.setTextSize(size); v.setPadding(0,8,0,8); return v;
    }

    private void buildUi() {
        LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(24,24,24,24); box.setBackgroundColor(Color.rgb(7,16,21));
        box.addView(text("Body Finder – RuView LEGACY NODE",20));
        TextView warning=text("EXPERIMENTAL RSSI NODE — NOT VALIDATED FOR RESCUE USE",11); warning.setTextColor(Color.rgb(255,180,84)); box.addView(warning);
        box.addView(text("Use this APK only if the full app cannot install. It participates in the same field fabric but has no radar UI.",12));
        LinearLayout row=new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        xInput=new EditText(this); xInput.setHint("x meters"); xInput.setText("0"); xInput.setTextColor(Color.WHITE); xInput.setHintTextColor(Color.GRAY); xInput.setInputType(2|8192); row.addView(xInput,new LinearLayout.LayoutParams(0,-2,1));
        yInput=new EditText(this); yInput.setHint("y meters"); yInput.setText("0"); yInput.setTextColor(Color.WHITE); yInput.setHintTextColor(Color.GRAY); yInput.setInputType(2|8192); row.addView(yInput,new LinearLayout.LayoutParams(0,-2,1));
        box.addView(row);
        Button set=new Button(this); set.setText("SET MEASURED POSITION"); set.setOnClickListener(v->{try{x=Double.parseDouble(xInput.getText().toString());y=Double.parseDouble(yInput.getText().toString());}catch(Exception ignored){}}); box.addView(set);
        Button cal=new Button(this); cal.setText("CALIBRATE EMPTY SCENE (8s)"); cal.setOnClickListener(v->calibrate(cal)); box.addView(cal);
        Button scan=new Button(this); scan.setText("START SCAN"); scan.setOnClickListener(v->{scanning=!scanning;scan.setText(scanning?"STOP SCAN":"START SCAN");}); box.addView(scan);
        Button share=new Button(this); share.setText("SHARE SNAPSHOT JSON"); share.setOnClickListener(v->shareSnapshot()); box.addView(share);
        status=text("Starting…",12); status.setTextIsSelectable(true); box.addView(status);
        ScrollView sc=new ScrollView(this); sc.addView(box); setContentView(sc);
    }

    @SuppressWarnings("deprecation") private Double rssi() {
        try {
            WifiManager wm=(WifiManager)getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if(wm==null||!wm.isWifiEnabled())return null;
            int v=wm.getConnectionInfo().getRssi();
            return (v>-127&&v<=0)?(double)v:null;
        } catch(Throwable t){ return null; }
    }

    private JSONObject probe(String state,String detail)throws JSONException{return new JSONObject().put("state",state).put("detail",detail);}
    private JSONObject capabilities() throws JSONException {
        return new JSONObject()
            .put("wifi_rssi",probe(rssi()!=null?"WORKING":"PROBE_FAILED","legacy connected-link Wi-Fi RSSI"))
            .put("wifi_rtt",probe("UNSUPPORTED","legacy adapter does not expose RTT"))
            .put("ble",probe("SUPPORTED_UNVERIFIED","BLE not used as human evidence in this build"))
            .put("imu",probe("SUPPORTED_UNVERIFIED","legacy node does not stream IMU yet"))
            .put("csi",probe("UNSUPPORTED","RSSI is never labeled CSI"))
            .put("udp_fabric",probe("WORKING_DEGRADED","multicast/broadcast requires field verification"))
            .put("compute",probe("WORKING_DEGRADED","legacy Android node"));
    }

    private JSONObject advertisement() throws JSONException {
        JSONObject j=new JSONObject();
        j.put("protocol_version",1);j.put("session_id",SESSION);j.put("node_id",nodeId);j.put("display_name",Build.MODEL+" legacy");j.put("platform","android-legacy");
        j.put("monotonic_ns",SystemClock.elapsedRealtimeNanos());j.put("coordinator_score",0.52);j.put("capabilities",capabilities());
        Double r=rssi();j.put("rssi_dbm",r==null?JSONObject.NULL:r);j.put("baseline_rssi_dbm",baseline==null?JSONObject.NULL:baseline);j.put("baseline_sigma_db",sigma==null?JSONObject.NULL:sigma);
        j.put("position",new JSONObject().put("x_m",x).put("y_m",y).put("z_m",0.0).put("sigma_m",0.35));j.put("scanning",scanning&&baseline!=null);
        return j;
    }

    private void calibrate(final Button button) {
        scanning=false;button.setEnabled(false);status.setText("CALIBRATING: keep target zone empty…");
        new Thread(()->{
            double sum=0,sum2=0;int n=0;
            for(int i=0;i<32;i++){Double r=rssi();if(r!=null){sum+=r;sum2+=r*r;n++;}try{Thread.sleep(250);}catch(InterruptedException ignored){}}
            if(n>=8){double m=sum/n;baseline=m;sigma=Math.max(1.0,Math.sqrt(Math.max(0,sum2/n-m*m)));}
            ui.post(()->{button.setEnabled(true);refreshStatus();});
        },"bf-calibrate").start();
    }

    private synchronized void expirePeers(){long now=System.currentTimeMillis();Iterator<Map.Entry<String,Long>> it=peers.entrySet().iterator();while(it.hasNext())if(now-it.next().getValue()>5000)it.remove();}

    private void refreshStatus() {
        expirePeers();
        String s=String.format(Locale.US,"node=%s\nmodel=%s API=%d\nRSSI=%s dBm\nbaseline=%s sigma=%s\nposition=(%.2f, %.2f) m\nscanning=%s\npeers=%d\nCSI=UNSUPPORTED\nnetwork=OPEN/UNTRUSTED",
            nodeId,Build.MODEL,Build.VERSION.SDK_INT,String.valueOf(rssi()),String.valueOf(baseline),String.valueOf(sigma),x,y,String.valueOf(scanning),peers.size());
        status.setText(s);
    }

    private void startFabric() {
        new Thread(()->{
            try {
                WifiManager wm=(WifiManager)getApplicationContext().getSystemService(Context.WIFI_SERVICE);
                if(wm!=null){multicastLock=wm.createMulticastLock("body-finder-legacy");multicastLock.setReferenceCounted(false);multicastLock.acquire();}
                MulticastSocket s=new MulticastSocket(null);socket=s;s.setReuseAddress(true);s.setBroadcast(true);s.bind(new InetSocketAddress(PORT));s.setSoTimeout(250);
                InetAddress group=InetAddress.getByName(GROUP);try{s.joinGroup(group);}catch(Throwable ignored){}
                InetAddress broad=InetAddress.getByName("255.255.255.255");byte[] buf=new byte[65507];long next=0;
                while(running){long now=System.currentTimeMillis();if(now>=next){byte[] b=advertisement().toString().getBytes(StandardCharsets.UTF_8);try{s.send(new DatagramPacket(b,b.length,group,PORT));}catch(Throwable ignored){}try{s.send(new DatagramPacket(b,b.length,broad,PORT));}catch(Throwable ignored){}next=now+1000;ui.post(this::refreshStatus);}
                    try{DatagramPacket p=new DatagramPacket(buf,buf.length);s.receive(p);JSONObject o=new JSONObject(new String(p.getData(),p.getOffset(),p.getLength(),StandardCharsets.UTF_8));String id=o.optString("node_id");if(o.optInt("protocol_version")==1&&SESSION.equals(o.optString("session_id"))&&!id.equals(nodeId)&&id.length()>0){synchronized(this){peers.put(id,System.currentTimeMillis());}}}catch(java.net.SocketTimeoutException ignored){}catch(Throwable ignored){}
                }
            }catch(Throwable t){ui.post(()->status.setText("Fabric error: "+t));}
        },"bf-fabric").start();
    }

    private void shareSnapshot(){try{String text=new JSONObject().put("report_version",1).put("truth","LIVE_RSSI_LEGACY_NODE_EXPERIMENTAL").put("advertisement",advertisement()).put("peer_count",peers.size()).toString(2);Intent i=new Intent(Intent.ACTION_SEND);i.setType("text/plain");i.putExtra(Intent.EXTRA_TEXT,text);startActivity(Intent.createChooser(i,"Body Finder result"));}catch(Throwable t){status.setText(String.valueOf(t));}}

    @Override protected void onDestroy(){running=false;try{if(socket!=null)socket.close();}catch(Throwable ignored){}try{if(multicastLock!=null&&multicastLock.isHeld())multicastLock.release();}catch(Throwable ignored){}super.onDestroy();}
}
