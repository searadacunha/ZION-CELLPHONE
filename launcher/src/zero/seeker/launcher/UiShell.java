package zero.seeker.launcher;

import android.app.UiAutomation;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.HandlerThread;
import android.os.Looper;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;

import java.io.PrintStream;
import java.lang.reflect.Constructor;

/**
 * Not part of the launcher's own life: this class is run as the shell user (adb, or Shizuku's rish from Termux), with
 * the launcher's APK as class path:
 *   app_process -Djava.class.path=$(pm path zero.seeker.launcher | cut -d: -f2) /system/bin zero.seeker.launcher.UiShell dump
 * OPERATOR's `ui` tool reads the screen with it.
 *
 * Why: Android's own `uiautomator dump` first waits for the screen to stop changing and gives up after 10 s on a
 * screen that never does ("ERROR: could not get idle state" on Settings > About phone, whose uptime ticks, on the
 * Seeker on 13/11). This reads the same accessibility tree at once, through the same UiAutomation connection the shell
 * command uses, and prints it in the same XML, so one parser reads both.
 *
 *   dump                  the active window, as `uiautomator dump` writes it (visible nodes only)
 *   text X Y BASE64       appends the UTF-8 text to the text field at that screen point (the shell's `input text`
 *                         only knows the keys of a plain keyboard: "é" makes it fail). A password field is refused,
 *                         unless a 5th word "secret" says OPERATOR allowed it (the owner dictated that password):
 *                         its content is then replaced.
 * Exit code 0 when done, 2 with a one-line reason otherwise.
 */
public final class UiShell {
    private static final int MAX_NODES = 4000;
    private static int count;

    public static void main(String[] args) {
        int code = 2;
        try {
            code = run(args);
        } catch (Throwable t) {
            System.err.println("UiShell: " + t);
        }
        System.out.flush();
        System.exit(code);  // the UiAutomation thread would keep the process alive
    }

    private static int run(String[] args) throws Exception {
        if (args.length == 0 || !(args[0].equals("dump") || (args[0].equals("text") && (args.length == 4 || args.length == 5)))) {
            System.err.println("usage: UiShell dump | text X Y BASE64 [secret]");
            return 2;
        }
        Looper.prepareMainLooper();  // Android's accessibility client builds a handler on it: without it, a null crash
        HandlerThread thread = new HandlerThread("zion-ui");
        thread.start();
        // the constructor and connect() are hidden from apps, not from a program the shell starts (uiautomator does this)
        Object link = Class.forName("android.app.UiAutomationConnection").getDeclaredConstructor().newInstance();
        Constructor<UiAutomation> make = UiAutomation.class.getDeclaredConstructor(
                Looper.class, Class.forName("android.app.IUiAutomationConnection"));
        make.setAccessible(true);
        UiAutomation ui = make.newInstance(thread.getLooper(), link);
        UiAutomation.class.getDeclaredMethod("connect").invoke(ui);
        try {
            // right after connect() Android often knows no active window yet (3 runs out of 8 on the Seeker, 13/11):
            // asked again for up to 2 s
            AccessibilityNodeInfo root = ui.getRootInActiveWindow();
            for (int i = 0; root == null && i < 25; i++) {
                Thread.sleep(80);
                root = ui.getRootInActiveWindow();
            }
            if (root == null) {
                System.err.println("UiShell: no active window");
                return 2;
            }
            if (args[0].equals("dump")) {
                StringBuilder out = new StringBuilder(1 << 15);
                out.append("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy>");
                node(root, 0, out);
                out.append("</hierarchy>");
                new PrintStream(System.out, false, "UTF-8").append(out).flush();
                return 0;
            }
            AccessibilityNodeInfo field = fieldAt(root, Integer.parseInt(args[1]), Integer.parseInt(args[2]));
            if (field == null) {
                System.err.println("UiShell: no text field at that point");
                return 2;
            }
            boolean secret = args.length == 5 && args[4].equals("secret");
            if (field.isPassword() != secret) {  // OPERATOR decides when a password may be typed, and says so here
                System.err.println("UiShell: password field and the word secret go together, refused");
                return 2;
            }
            CharSequence had = secret || field.isShowingHintText() ? "" : field.getText();
            Bundle b = new Bundle();
            b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    (had == null ? "" : had.toString()) + new String(Base64.decode(args[3], Base64.DEFAULT), "UTF-8"));
            if (!field.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, b)) {
                System.err.println("UiShell: the field refused the text");
                return 2;
            }
            return 0;
        } finally {
            try {
                UiAutomation.class.getDeclaredMethod("disconnect").invoke(ui);
            } catch (Throwable ignored) {
            }
        }
    }

    private static void node(AccessibilityNodeInfo n, int index, StringBuilder out) {
        if (++count > MAX_NODES) return;
        Rect r = new Rect();
        n.getBoundsInScreen(r);
        out.append("<node index=\"").append(index).append('"');
        attr(out, "text", n.getText());
        attr(out, "resource-id", n.getViewIdResourceName());
        attr(out, "class", n.getClassName());
        attr(out, "package", n.getPackageName());
        attr(out, "content-desc", n.getContentDescription());
        flag(out, "checkable", n.isCheckable());
        flag(out, "checked", n.isChecked());
        flag(out, "clickable", n.isClickable());
        flag(out, "enabled", n.isEnabled());
        flag(out, "focusable", n.isFocusable());
        flag(out, "focused", n.isFocused());
        flag(out, "scrollable", n.isScrollable());
        flag(out, "long-clickable", n.isLongClickable());
        flag(out, "password", n.isPassword());
        flag(out, "selected", n.isSelected());
        flag(out, "editable", n.isEditable());  // not in uiautomator's dump: a search box is no EditText by its class name
        out.append(" bounds=\"[").append(r.left).append(',').append(r.top).append("][")
                .append(r.right).append(',').append(r.bottom).append("]\"");
        attr(out, "hint", n.getHintText());
        out.append('>');
        for (int i = 0, k = n.getChildCount(); i < k; i++) {
            AccessibilityNodeInfo c = n.getChild(i);
            if (c != null && c.isVisibleToUser()) node(c, i, out);
        }
        out.append("</node>");
    }

    private static AccessibilityNodeInfo fieldAt(AccessibilityNodeInfo n, int x, int y) {
        Rect r = new Rect();
        n.getBoundsInScreen(r);
        if (!r.contains(x, y)) return null;
        for (int i = 0, k = n.getChildCount(); i < k; i++) {  // the deepest field under the point
            AccessibilityNodeInfo c = n.getChild(i);
            AccessibilityNodeInfo hit = c == null ? null : fieldAt(c, x, y);
            if (hit != null) return hit;
        }
        return n.isEditable() ? n : null;
    }

    private static void flag(StringBuilder out, String name, boolean v) {
        out.append(' ').append(name).append("=\"").append(v).append('"');
    }

    private static void attr(StringBuilder out, String name, CharSequence v) {
        out.append(' ').append(name).append("=\"");
        for (int i = 0, k = v == null ? 0 : v.length(); i < k; i++) {
            char c = v.charAt(i);
            if (c == '&') out.append("&amp;");
            else if (c == '<') out.append("&lt;");
            else if (c == '>') out.append("&gt;");
            else if (c == '"') out.append("&quot;");
            else if (c == '\n' || c == '\r' || c == '\t') out.append(' ');
            else if (c >= 0x20 && c != 0xFFFE && c != 0xFFFF && !Character.isSurrogate(c)) out.append(c);
            else if (Character.isHighSurrogate(c) && i + 1 < k && Character.isLowSurrogate(v.charAt(i + 1)))
                out.append(c).append(v.charAt(++i));  // a whole emoji; a lone half or a control character is dropped
        }
        out.append('"');
    }
}
