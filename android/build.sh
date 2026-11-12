#!/bin/bash
# Construye la app nativa UMA-Mercure sin Gradle ni Android Studio.
# Requiere: build-tools 35.x, platforms android-35 (android.jar), JDK con javac/d8 accesible.
# Edita las tres rutas (o expórtalas) y ejecuta: bash build.sh
set -e

BT="${ANDROID_BUILD_TOOLS:-$HOME/Android/build-tools/35.0.0}"
AJ="${ANDROID_PLATFORM_JAR:-$HOME/Android/platforms/android-35/android.jar}"
KS="${DEBUG_KEYSTORE:-$HOME/.android/debug.keystore}"
KS_PASS="${DEBUG_KEYSTORE_PASS:-pass:android}"
B="$(cd "$(dirname "$0")" && pwd)"

[ -f "$AJ" ] || { echo "Falta android.jar: $AJ (instala el platform android-35)"; exit 1; }
[ -f "$KS" ] || { echo "Falta keystore: $KS (crea uno: keytool -genkey -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android -keyalg RSA -keysize 2048 -validity 10000)"; exit 1; }

cd "$B"
rm -rf out && mkdir -p out
"$BT/aapt2" compile --dir res -o out/res.zip
"$BT/aapt2" link -o out/base.apk --manifest AndroidManifest.xml -I "$AJ" --java out/gen out/res.zip
javac -classpath "$AJ" -d out/classes $(find src out/gen -name '*.java') 2>&1 | grep -v deprecat || true
"$BT/d8" --min-api 26 --output out $(find out/classes/com -name '*.class' -not -name 'R.class' -not -name 'R$*')
cp out/base.apk out/unsigned.apk
(cd out && zip -q unsigned.apk classes.dex)
"$BT/zipalign" -f 4 out/unsigned.apk out/aligned.apk
"$BT/apksigner" sign --ks "$KS" --ks-pass "$KS_PASS" --ks-key-alias androiddebugkey --key-pass "$KS_PASS" --out out/uma-radio.apk out/aligned.apk
echo "APK: out/uma-radio.apk ($(stat -c%s out/uma-radio.apk) bytes)"
echo "Instalar por USB:  adb install -r out/uma-radio.apk"
echo "O servirla desde la propia radio para instalar en el movil: cp out/uma-radio.apk ../web/dist/uma-radio.apk"
