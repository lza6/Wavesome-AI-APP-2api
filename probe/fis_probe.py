import json, urllib.request
UA="okhttp/4.9.3"
API="AIzaSyDTH4p7K3SmKiH-gVvzsN7YHoP1I9k7kfA"
APPID="1:676955275610:android:11f8fd986389a3dff07363"
PKG="com.wave.wavesome.ai.image.generator"
CERT="2412F88AC73778C3D659D47A3112E27898F953B9"
def call(url, body, headers, raw=False):
    data = body if raw else json.dumps(body).encode()
    req=urllib.request.Request(url, data=data, headers={"User-Agent":UA, "Content-Type":"application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return (r.status, r.headers.get("content-type"), r.read())
    except urllib.error.HTTPError as e: return (e.code, None, e.read())
st,ct,b=call("https://firebaseinstallations.googleapis.com/v1/projects/wavesome-ai/installations",
    {"appId":APPID,"authVersion":"FIS_v2","sdkVersion":"a:17.1.0"},
    {"x-goog-api-key":API,"X-Android-Package":PKG,"X-Android-Cert":CERT})
d=json.loads(b); fid=d["fid"]; auth=d["authToken"]["token"]
print("fid",fid, "auth len", len(auth))
gen={"prompt":"a cat","uuid":"89d874da-2dd4-4488-aad6-a1eed5b1c3b3","width":512,"height":512,"aspect_ratio":"1:1","restore_faces":False}
U="https://ailwapi360.waveabc.xyz/api/service/generate"
for label,tok in [("fis_auth",auth),("fid",fid)]:
    s,ct,body=call(U, gen, {"api-version":"31","device-token":tok})
    print(label, s, ct, body[:150])
