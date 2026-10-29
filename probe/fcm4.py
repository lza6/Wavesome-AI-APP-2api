import json, urllib.request, re
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
H={"x-goog-api-key":API,"x-goog-firebase-installations-auth":auth}
U="https://fcmregistrations.googleapis.com/v1/projects/wavesome-ai/registrations"
cands=["package_name","certificate","fid","sdk_version","auth_version","app_id","appId","app_name","application_id",
 "installation_id","installation","token","subtype","cert_sha1","certSha1","signature","sha1","sha_1","cert",
 "project_id","api_key","gcm_sender_id","sender_id","senderId","topics","platform","user_agent","os_version",
 "endpoint","keys","p256dh","applicationPubKey","auth_secret","authSecret","web","android","ios","device_id",
 "device_token","instance_id","fis","fis_token","firebase_installation_id","firebaseInstallationId","use_installations"]
body={"android":{k:"probe" for k in cands}}
s,r=post(U, body, H)
unknown=set(re.findall(r'Unknown name \\"([^\\"]+)\\" at', r))
print("status", s)
print("unknown:", sorted(unknown))
print("KNOWN:", [k for k in cands if k not in unknown])
print("raw:", r[:400])
