package zero.seeker.testbed;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.text.InputType;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.*;

public class Main extends Activity {
    EditText nom, qte;
    Switch mode;
    CheckBox ok;
    TextView status;
    boolean binding;

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        State.load(this);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        ScrollView sv = new ScrollView(this);
        sv.addView(col);
        State.insets(sv);
        TextView title = new TextView(this);
        title.setText("ZION TESTBED");
        title.setTextSize(24);
        col.addView(title);
        nom = field("Nom", InputType.TYPE_CLASS_TEXT);
        qte = field("Quantité", InputType.TYPE_CLASS_NUMBER);
        nom.addTextChangedListener(new Watch(() -> State.nom = nom.getText().toString()));
        qte.addTextChangedListener(new Watch(() -> State.quantite = qte.getText().toString()));
        col.addView(nom);
        col.addView(qte);
        mode = new Switch(this);
        mode.setText("Mode test");
        mode.setOnCheckedChangeListener((v, on) -> change(() -> State.modeTest = on));
        col.addView(mode);
        ok = new CheckBox(this);
        ok.setText("J'accepte");
        ok.setOnCheckedChangeListener((v, on) -> change(() -> State.accepte = on));
        col.addView(ok);
        col.addView(button("Valider", () -> State.valide++));
        col.addView(button("Liste", () -> startActivity(new Intent(this, ListAct.class))));
        col.addView(button("Messages", () -> startActivity(new Intent(this, Messages.class))));
        col.addView(button("Remise à zéro", () -> { State.reset(this); show(); }));
        status = new TextView(this);
        col.addView(status);
        setContentView(sv);
        if (getIntent().getBooleanExtra("reset", false)) State.reset(this);
    }

    @Override protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        setIntent(i);
        if (i.getBooleanExtra("reset", false)) State.reset(this);
    }

    @Override protected void onResume() {
        super.onResume();
        State.ecran = "main";
        State.save(this);
        show();
    }

    EditText field(String label, int type) {
        EditText e = new EditText(this);
        e.setHint(label);
        e.setContentDescription(label);
        e.setInputType(type);
        e.setSingleLine(true);
        return e;
    }

    Button button(String label, Runnable r) {
        Button x = new Button(this);
        x.setText(label);
        x.setAllCaps(false);
        x.setOnClickListener(v -> change(r));
        return x;
    }

    /** Apply a change, mirror it to state.json and redraw the status line. */
    void change(Runnable r) {
        if (binding) return;
        r.run();
        State.save(this);
        showStatus();
    }

    void show() {
        binding = true;
        nom.setText(State.nom);
        qte.setText(State.quantite);
        mode.setChecked(State.modeTest);
        ok.setChecked(State.accepte);
        binding = false;
        showStatus();
    }

    void showStatus() {
        status.setText("ÉTAT: nom=" + State.nom + " quantité=" + State.quantite + " test=" + State.modeTest
            + " accepte=" + State.accepte + " valide=" + State.valide + " sélection=" + (State.selection < 0 ? "-" : "" + State.selection));
    }

    final class Watch implements TextWatcher {
        final Runnable r;
        Watch(Runnable r) { this.r = r; }
        public void beforeTextChanged(CharSequence s, int a, int b, int c) {}
        public void onTextChanged(CharSequence s, int a, int b, int c) {}
        public void afterTextChanged(Editable e) { change(r); }
    }
}
