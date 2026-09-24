"""
課程題庫的門禁。

課程題目(Python / Deep Learning / AI 導論 / VBA / EMBA)是上課教材。
學生在老師開的考坊裡看到當場那 20 題沒問題,不能被整包撈走的是「整個題庫」。

會漏的路有兩條,都在這裡堵:
  1. POST /api/start      單人練習,一次吐 10 題,原本沒有任何驗證
  2. POST /api/mp/create  任何人都能自己開一間考坊,一題一題翻完

學生走的那條路完全不受影響:他們是 /play → /api/mp/join → /api/mp/view,
而 multiplayer 的 public_question() 一次只發當前那一題,不帶 id 也不帶答案,
reveal 的答案只在該題結束後才出現,一場最多 20 題。

密碼放環境變數 TEACH_CODE,不寫進任何檔案 —— repo 是公開的。

三種狀態:
  TEACH_CODE 有設              → 課程主題一律要先解鎖
  沒設,而且在本機跑            → 課程主題直接開放(維持你原本的使用習慣,零設定)
  沒設,而且在雲端(RENDER=true) → 課程主題完全關閉,也解不開
                                 寧可你發現「咦課程不見了」,也不要以為鎖好了其實沒鎖
"""
import hmac
import os
import secrets
import time

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# 這幾個主題的題目是課程教材
COURSE_TOPICS = ("python", "pytorch", "ai", "vba", "emba")

COOKIE = "pulse_teach"
MAX_AGE = 12 * 60 * 60            # 解鎖後 12 小時內不用再輸入

TEACH_CODE = (os.environ.get("TEACH_CODE") or "").strip()
ON_CLOUD = bool(os.environ.get("RENDER"))      # Render 一定會設 RENDER=true

# 簽 cookie 用的鑰匙。沒設就每次啟動隨機產生一把 ——
# 代表伺服器重開之後要重新解鎖,對一個人用的主持台來說完全可以接受。
_SECRET = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
_signer = URLSafeTimedSerializer(_SECRET, salt="pulse-teach")


def is_course(topic):
    return topic in COURSE_TOPICS


def enforced():
    """這個站台有沒有在管制課程題庫"""
    return bool(TEACH_CODE) or ON_CLOUD


def openable():
    """管制中的站台,有沒有辦法解鎖(沒設 TEACH_CODE 的雲端是解不開的)"""
    return bool(TEACH_CODE)


def unlocked(req):
    """這個請求有沒有通過門禁"""
    if not enforced():
        return True                       # 本機零設定,照舊全開
    if not openable():
        return False                      # 雲端忘了設 TEACH_CODE → 一律擋掉
    tok = req.cookies.get(COOKIE)
    if not tok:
        return False
    try:
        _signer.loads(tok, max_age=MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def allow(topic, req):
    """這個主題,這個請求能不能碰"""
    return not is_course(topic) or unlocked(req)


def check_code(given):
    """比對密碼。用 compare_digest,不要讓回應時間洩漏資訊"""
    if not openable():
        return False
    return hmac.compare_digest(str(given or "").strip().encode(), TEACH_CODE.encode())


def make_token():
    return _signer.dumps({"t": int(time.time())})


def status(req):
    """給前端看的狀態"""
    return {"enforced": enforced(), "openable": openable(),
            "unlocked": unlocked(req), "topics": list(COURSE_TOPICS)}


# ---------------------------------------------------------------- 速率限制
# 只用在「試解鎖碼」這一件事上,防人硬猜密碼。
#
# 原本也想順手限制 /api/start 和 /api/mp/create,後來拿掉了:
# 整班學生是在同一個校園 NAT 後面,伺服器看到的是同一個 IP。
# 55 個人同時開局就是 55 次請求,任何合理的門檻都會誤傷整班。
# 真正的防線是 cookie 門禁(擋的是「身分」不是「次數」),那個不會誤傷任何人。
_HITS = {}
_WINDOW = 60
_MAX = 10


def too_fast(key, limit=_MAX):
    now = time.time()
    if len(_HITS) > 5000:                  # 防止字典無限長大
        for k, v in list(_HITS.items()):
            if not v or now - v[-1] > _WINDOW:
                _HITS.pop(k, None)
    hits = [t for t in _HITS.get(key, []) if now - t < _WINDOW]
    hits.append(now)
    _HITS[key] = hits
    return len(hits) > limit


def reset_limits():
    """測試用"""
    _HITS.clear()
