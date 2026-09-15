STREAM = "pings"
GROUP = "writers"
PAYLOAD_FIELD = b"p"

NEW_MESSAGES = ">"
PENDING_MESSAGES = "0"
GROUP_EXISTS_PREFIX = "BUSYGROUP"

READ_COUNT = 4
BLOCK_MS = 200

POSITION_FLUSH_JITTER_S = 0.25

CLAIM_IDLE_MS = 30_000
CLAIM_INTERVAL_S = 10.0
CLAIM_JITTER_S = 2.0

DEVICE_ZONES_KEY = "inside:{device_id}"
PENDING_PINGS_KEY = "pings:pending"

RETENTION_MAX_PASSES = 100

SUPERVISOR_CHECK_INTERVAL_S = 5.0
SUPERVISOR_RESTART_DELAY_S = 1.0
TASK_STALL_TIMEOUT_S = 60.0
FLAPPING_WINDOW_S = 120.0
FLAPPING_RESTARTS = 3

RETRY_AFTER_S = 1

RETRY_BACKOFF_S = 0.5
RETRY_BACKOFF_MAX_S = 15.0

SYNC_ZONES_LUA = """
local key = KEYS[1]
local ttl = tonumber(ARGV[1])
local current = {}
for i = 2, #ARGV do
    current[ARGV[i]] = true
end

for _, zone in ipairs(redis.call('SMEMBERS', key)) do
    if not current[zone] then
        redis.call('SREM', key, zone)
    end
end

local entered = {}
for i = 2, #ARGV do
    if redis.call('SADD', key, ARGV[i]) == 1 then
        entered[#entered + 1] = ARGV[i]
    end
end

if redis.call('SCARD', key) > 0 then
    redis.call('EXPIRE', key, ttl)
else
    redis.call('DEL', key)
end

return entered
"""
