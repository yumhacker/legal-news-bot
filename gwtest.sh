#!/usr/bin/env bash
# Диагностика доступа к API gov.il с сервера: bash gwtest.sh
K='x-client-id: 9KFgciHHGDyNiqz5MdQS0eK2ApeJYMc6YnElUICpN1atirZc'
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
GW='https://openapi-gc.digital.gov.il/pub/cio/govil/rest/collectors/v1/api/DataCollector/GetResults?CollectorType=news&officeId=95b283ad-fc02-40e6-ac6f-8986acac6b86&culture=he'
POL='https://www.gov.il/he/api/PolicyApi/Index?OfficeId=95b283ad-fc02-40e6-ac6f-8986acac6b86&Type=2efa9b53-5df9-4df9-8e9d-21134511f368&limit=2'

t() {
  label="$1"; shift
  out=$(wget -qO- --timeout=20 "$@" 2>/dev/null | head -c 130)
  rc=$?
  echo "== $label rc=$rc: ${out:0:130}"
}

t "GW key"               --header="$K" "$GW"
t "GW key+ref"           --header="$K" --header='Referer: https://www.gov.il/' --header='Origin: https://www.gov.il' "$GW"
t "GW key+ref+UA"        --user-agent="$UA" --header="$K" --header='Referer: https://www.gov.il/' --header='Origin: https://www.gov.il' "$GW"
t "GW key+UA+accept"     --user-agent="$UA" --header="$K" --header='Accept: application/json, text/plain, */*' --header='Accept-Language: he' "$GW"
t "POL plain"            "$POL"
t "POL UA"               --user-agent="$UA" "$POL"
t "POL UA+ref"           --user-agent="$UA" --header='Referer: https://www.gov.il/he/collectors/policies' "$POL"
echo "DIAG-DONE"
