package zero.seeker.launcher;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** The key of OPERATOR's service for the "ai" screen (seeker-ai --serve), sent by Termux at each start of the service and
 *  again when the screen shows an old one. The manifest lets only Termux send it: the sender must hold Termux's own
 *  signature permission. Kept in this app's private storage. */
public class AiToken extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent i) {
        String key = i.getStringExtra("token");
        int port = i.getIntExtra("port", 0);
        if (!"zero.seeker.launcher.AI_TOKEN".equals(i.getAction()) || key == null || key.length() < 20
            || !key.matches("[A-Za-z0-9_-]+") || port < 1024 || port > 65535) return;
        c.getSharedPreferences("ai", Context.MODE_PRIVATE).edit().putString("token", key).putInt("port", port).apply();
    }
}
