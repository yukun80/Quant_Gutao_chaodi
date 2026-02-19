python - <<'PY'
from src.config import get_settings
from src.models import AlertEvent
from src.notifier import NotificationGateway

s = get_settings()
gw = NotificationGateway(s.DINGTALK_URL, keyword=s.DINGTALK_KEYWORD)
ok = gw.send_alert(AlertEvent(
    code="600000", name="测试", pool_type="all",
    initial_ask_v1=1000, current_ask_v1=600, drop_ratio=0.4
))
print("dingtalk send:", ok)
PY

python - <<'PY'
from src.config import get_settings
s = get_settings()
print("config ok:", bool(s.TUSHARE_TOKEN), bool(s.DINGTALK_URL), s.BACKTEST_SOURCE)
PY

bash scripts/backtest_joinquant_smoke.sh 2025-11-05 002122


python - <<'PY'
from src.config import get_settings
import apprise

s = get_settings()
app = apprise.Apprise()
ok_add = app.add(s.DINGTALK_URL)
ok_send = app.notify(title="test", body=f"{s.DINGTALK_KEYWORD}\n连通性测试")
print("add:", ok_add, "send:", ok_send)
PY