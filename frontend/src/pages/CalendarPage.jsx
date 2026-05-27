import ResultsCalendar from "../components/ResultsCalendar"
import AnnouncementFeed from "../components/AnnouncementFeed"

export default function CalendarPage({ symbol, onAnalyze }) {
  return (
    <div className="flex h-full overflow-hidden">

      {/* Left: Results Calendar - takes 60% width */}
      <div className="flex-1 overflow-auto border-r border-mp-border">
        <div className="px-4 py-3 border-b border-mp-border
                        flex items-center gap-2 sticky top-0
                        bg-mp-surface z-10">
          <span className="text-xs font-bold text-mp-muted
                           tracking-widest uppercase">
            📅 Results Calendar
          </span>
        </div>
        <ResultsCalendar onAnalyze={onAnalyze} />
      </div>

      {/* Right: Announcement Feed - takes 40% width */}
      <div className="w-80 flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-mp-border
                        flex items-center gap-2 sticky top-0
                        bg-mp-surface z-10">
          <div className="w-2 h-2 rounded-full bg-mp-green
                          animate-pulse" />
          <span className="text-xs font-bold text-mp-muted
                           tracking-widest uppercase">
            Live Feed
          </span>
        </div>
        <div className="flex-1 overflow-auto">
          <AnnouncementFeed onAnalyze={onAnalyze} />
        </div>
      </div>

    </div>
  )
}
