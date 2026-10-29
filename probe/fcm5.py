import json, urllib.request
API="AIzaSyDTH4p7K3SmKiH-gVvzsN7YHoP1I9k7kfA"; APPID="1:676955275610:android:11f8fd986389a3dff07363"
PKG="com.wave.wavesome.ai.image.generator"; CERT="2412F88AC73778C3D659D47A3112E27898F953B9"
def post(url, body, headers):
    req=urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
st,b=post("https://firebaseinstallations.googleapis.com/v1/projects/wavesome-ai/installations",
    {"appId":APPID,"authVersion":"FIS_v2","sdkVersion":"a:17.1.0"},
    {"x-goog-api-key":API,"X-Android-Package":PKG,"X-Android-Cert":CERT})
d=json.loads(b); fid=d["fid"]; auth=d["authToken"]["token"]
print("fid",fid)
for headers in [
   {"x-goog-api-key":API,"x-goog-firebase-installations-auth":auth},
   {"x-goog-api-key":API,"x-goog-firebase-installations-auth":auth,"X-Android-Package":PKG,"X-Android-Cert":CERT},
]:
    for url in ["https://fcmregistrations.googleapis.com/v1/projects/wavesome-ai/registrations",
                "https://fcmregistrations.googleapis.com/v1/projects/676955275610/registrations"]:
        s,r=post(url, {"android":{"package_name":PKG}}, headers)
        print(f"--- {url.split('/')[-2]} hdr{len(headers)}: {s} {r[:300]}")
