package zero.seeker.launcher;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Termux asks for the owner's approval (extra "req": the request JSON, see ApprovalFormat.parse) or withdraws one
 *  (extra "cancel": its id). As for AiToken, the manifest lets only Termux send it (Termux's own signature permission).
 *  `am broadcast` prints the answer: result=-1 with "ok <id>" or "cancelled <id>", else result=1 with the reason. */
public class ApprovalAsk extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent i) {
        if (!"zero.seeker.launcher.APPROVAL_ASK".equals(i.getAction())) return;
        Context c = context.getApplicationContext();
        String req = i.getStringExtra("req"), cancel = i.getStringExtra("cancel");
        PendingResult answer = goAsync();
        new Thread(() -> {
            int code = 1;
            String say;
            try {
                if (cancel != null) {
                    boolean had = ApprovalFormat.cancel(Approve.dir(c), cancel);
                    say = had ? "cancelled " + cancel : "refused: no pending request with this id";
                    if (had) code = -1;
                } else {
                    say = "ok " + ApprovalFormat.intake(Approve.dir(c), req, Approve.now());
                    code = -1;
                }
            } catch (Exception e) {  // IllegalArgumentException: what is wrong with the request
                say = "refused: " + e.getMessage();
            }
            answer.setResult(code, say, null);
            Approve.notifyPending(c, cancel == null && code == -1);
            answer.finish();
            try {
                Approve.ensureKey(c);  // approval.pub exists before the first approval: Termux enrolls it
            } catch (Exception ignored) {  // the approval screen says what is wrong
            }
        }).start();
    }
}
