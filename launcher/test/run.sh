#!/bin/sh
# Test of the launcher's approval format on a plain JDK (no Android): the same ApprovalFormat.java as the app.
# The vectors go to a temporary file; to write the committed ones again: launcher/test/run.sh tests/approval_vectors.json
# JDK: Homebrew's 17 as in build.sh when present, else $JAVA_HOME, else the PATH (CI runners).
d=$(cd "$(dirname "$0")/.." && pwd)
j=/opt/homebrew/opt/openjdk@17/bin
[ -x "$j/javac" ] || j=${JAVA_HOME:+$JAVA_HOME/bin}
o=$(mktemp -d)
"${j:+$j/}javac" --release 11 -d "$o" "$d/src/zero/seeker/launcher/ApprovalFormat.java" "$d/test/ApprovalVectorTest.java" &&
  "${j:+$j/}java" -cp "$o" zero.seeker.launcher.ApprovalVectorTest "${1:-$o/approval_vectors.json}"
s=$?
rm -rf "$o"
exit $s
