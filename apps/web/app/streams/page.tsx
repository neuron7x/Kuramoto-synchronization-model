import { getRealtimeStreamUrl } from '../lib/api'
import { RealtimeStreamViewer } from '../components/realtime-stream-viewer'

export const dynamic = 'force-dynamic'

export default function StreamsPage() {
  const websocketUrl = getRealtimeStreamUrl()

  return (
    <main className="tp-main">
      <div className="tp-main__container">
        <header className="tp-page-header">
          <h1 className="tp-page-title">Realtime stream</h1>
          <p className="tp-page-description">
            Subscribe to the analytics websocket feed exposed by the backend service to monitor kill-switches and market insights
            in real time.
          </p>
        </header>

        <section className="panel" data-testid="realtime-section">
          <RealtimeStreamViewer url={websocketUrl} />
        </section>
      </div>
    </main>
  )
}
