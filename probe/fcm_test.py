import json, uuid, urllib.request, gzip

API="AIzaSyDTH4p7K3SmKiH-gVvzsN7YHoP1I9k7kfA"
APPID="1:676955275610:android:11f8fd986389a3dff07363"
PKG="com.wave.wavesome.ai.image.generator"
CERT="2412F88AC73778C3D659D47A3112E27898F953B9"

def post(url, body, headers):
    req=urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def fis():
    st, body = post("https://firebaseinstallations.googleapis.com/v1/projects/wavesome-ai/installations",
        {"appId":APPID,"authVersion":"FIS_v2","sdkVersion":"a:17.1.0"},
        {"x-goog-api-key":API,"X-Android-Package":PKG,"X-Android-Cert":CERT})
    d=json.loads(body)
    return d["fid"], d["authToken"]["token"]

fid, auth = fis()
print("fid", fid)
targets = [
  ("flat_snake", {"app_id":APPID,"fid":fid,"sdk_version":"a:17.1.0"}),
  ("nested_reg", {"registration":{"app_id":APPID,"fid":fid,"sdk_version":"a:17.1.0"}}),
  ("flat_camel", {"appId":APPID,"fid":fid,"sdkVersion":"a:17.1.0"}),
  ("android_wrap", {"android":{"app_id":APPID,"fid":fid,"sdk_version":"a:17.1.0"}}),
]
for name, body in targets:
    st, resp = post("https://fcmregistrations.googleapis.com/v1/projects/wavesome-ai/registrations", body,
        {"x-goog-api-key":API,"x-goog-firebase-installations-auth":auth})
    print(f"--- {name}: {st} {resp[:280]}")
