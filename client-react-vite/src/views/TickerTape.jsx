/**
 * Situational-awareness marquee at the top of the dashboard.
 *
 * Renders release countdowns, active warnings, COT print, stale flags, and
 * last-ingest timestamp as a continuously scrolling tape. Pauses on hover so
 * traders can read a specific item.
 */
export function TickerTape({ tape }) {
  const items = tape?.items ?? []
  if (!items.length) return null

  // Duplicate items once so the CSS marquee loops seamlessly with a single
  // `translateX(-50%)` step — no JS animation frame math needed.
  const doubled = [...items, ...items]

  return (
    <div className="ticker-tape" role="marquee" aria-label="Market awareness tape">
      <div className="ticker-tape__track">
        {doubled.map((item, index) => (
          <TickerItem key={`${item.type}-${index}`} item={item} />
        ))}
      </div>
    </div>
  )
}

function TickerItem({ item }) {
  switch (item.type) {
    case 'release_countdown':
      return <ReleaseCountdownItem item={item} />
    case 'cot_print':
      return <CotPrintItem item={item} />
    case 'warning':
      return <WarningItem item={item} />
    case 'stale':
      return <StaleItem item={item} />
    case 'ingest':
      return <IngestItem item={item} />
    default:
      return null
  }
}

function ReleaseCountdownItem({ item }) {
  const when = formatCountdown(item.days_until, item.hours_until)
  const stamp = formatReleaseStamp(item.released_at_et)
  return (
    <span className="ticker-item ticker-item--countdown">
      <span className="ticker-item__tag">NEXT</span>
      <span className="ticker-item__body">
        {item.source} <span className="ticker-item__mono">· {stamp} · {when}</span>
      </span>
    </span>
  )
}

function CotPrintItem({ item }) {
  const netFmt = formatSignedThousands(item.managed_money_net)
  const wowFmt = formatSignedThousands(item.managed_money_net_wow, { withPlus: true })
  const wowClass = deltaClass(item.managed_money_net_wow)
  return (
    <span className="ticker-item ticker-item--print">
      <span className="ticker-item__tag">COT</span>
      <span className="ticker-item__body">
        {item.contract} MM net{' '}
        <span className="ticker-item__mono">{netFmt}</span>
        {wowFmt ? (
          <>
            {' '}
            <span className={`ticker-item__delta ticker-item__delta--${wowClass}`}>
              {wowFmt} WoW
            </span>
          </>
        ) : null}
      </span>
    </span>
  )
}

function WarningItem({ item }) {
  return (
    <span className={`ticker-item ticker-item--warning ticker-item--warning-${item.severity}`}>
      <span className="ticker-item__tag">ALERT</span>
      <span className="ticker-item__body">
        {prettySignalType(item.signal_type)} — {item.message}
      </span>
    </span>
  )
}

function StaleItem({ item }) {
  return (
    <span className="ticker-item ticker-item--stale">
      <span className="ticker-item__tag">STALE</span>
      <span className="ticker-item__body">
        {item.label} <span className="ticker-item__mono">{item.age_days}d</span>
      </span>
    </span>
  )
}

function IngestItem({ item }) {
  return (
    <span className="ticker-item ticker-item--ingest">
      <span className="ticker-item__tag">INGEST</span>
      <span className="ticker-item__body">
        Last <span className="ticker-item__mono">{formatIngestStamp(item.finished_at)}</span>
      </span>
    </span>
  )
}

/* ---------- formatters ---------- */

function formatCountdown(days, hours) {
  if (days >= 1) return `in ${days}d`
  if (hours >= 1) return `in ${hours}h`
  return 'imminent'
}

function formatReleaseStamp(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: 'America/New_York',
  }) + ' ET'
}

function formatIngestStamp(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}

function formatSignedThousands(value, { withPlus = false } = {}) {
  if (value == null || Number.isNaN(value)) return null
  const rounded = Math.round(value / 1000)
  if (rounded === 0) return '0k'
  const sign = rounded > 0 ? (withPlus ? '+' : '') : ''
  return `${sign}${rounded.toLocaleString()}k`
}

function deltaClass(value) {
  if (value == null || value === 0) return 'flat'
  return value > 0 ? 'up' : 'down'
}

function prettySignalType(type) {
  if (!type) return ''
  return type.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
