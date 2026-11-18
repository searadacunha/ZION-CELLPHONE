package zero.seeker.testbed;

import android.app.Activity;
import android.os.Bundle;
import android.widget.*;

public class ListAct extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        State.load(this);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        State.insets(col);
        TextView title = new TextView(this);
        title.setText("LISTE");
        title.setTextSize(24);
        col.addView(title);
        String[] rows = new String[30];
        for (int i = 0; i < 30; i++) rows[i] = "Élément " + (i + 1);
        ListView lv = new ListView(this);
        lv.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, rows));
        lv.setOnItemClickListener((p, v, pos, id) -> { State.selection = pos + 1; State.save(this); finish(); });
        col.addView(lv, new LinearLayout.LayoutParams(-1, 0, 1f));
        setContentView(col);
    }

    @Override protected void onResume() {
        super.onResume();
        State.ecran = "liste";
        State.save(this);
    }
}
