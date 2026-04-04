import EventKit
import Foundation

struct CalendarEventRecord: Codable {
    let calendar_name: String
    let title: String
    let location: String
    let start_at: String
    let end_at: String
    let all_day: Bool
}

enum CalendarQueryError: LocalizedError {
    case invalidArguments
    case invalidDate(String)
    case accessTimedOut
    case accessDenied(String)

    var errorDescription: String? {
        switch self {
        case .invalidArguments:
            return "start/end ISO8601 인자가 필요합니다."
        case .invalidDate(let value):
            return "잘못된 날짜 형식입니다: \(value)"
        case .accessTimedOut:
            return "Calendar 접근 권한 응답이 지연되었습니다."
        case .accessDenied(let message):
            if !message.isEmpty {
                return message
            }
            return "Calendar 접근 권한이 없습니다. 시스템 설정 > 개인정보 보호 및 보안 > 캘린더에서 Terminal, iTerm, Warp 또는 현재 백엔드를 실행한 앱의 권한을 허용해 주세요."
        }
    }
}

func fail(_ error: Error) -> Never {
    let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
    FileHandle.standardError.write(Data(message.utf8))
    FileHandle.standardError.write(Data("\n".utf8))
    exit(1)
}

func parseDate(_ raw: String, formatter: ISO8601DateFormatter) throws -> Date {
    if let value = formatter.date(from: raw) {
        return value
    }
    throw CalendarQueryError.invalidDate(raw)
}

do {
    guard CommandLine.arguments.count >= 3 else {
        throw CalendarQueryError.invalidArguments
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]

    let startAt = try parseDate(CommandLine.arguments[1], formatter: formatter)
    let endAt = try parseDate(CommandLine.arguments[2], formatter: formatter)

    let store = EKEventStore()
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    var accessError: Error?

    if #available(macOS 14.0, *) {
        store.requestFullAccessToEvents { value, error in
            granted = value
            accessError = error
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .event) { value, error in
            granted = value
            accessError = error
            semaphore.signal()
        }
    }

    if semaphore.wait(timeout: .now() + 10) == .timedOut {
        throw CalendarQueryError.accessTimedOut
    }

    if !granted {
        throw CalendarQueryError.accessDenied(accessError?.localizedDescription ?? "")
    }

    let predicate = store.predicateForEvents(withStart: startAt, end: endAt, calendars: nil)
    let records = store.events(matching: predicate)
        .sorted {
            if $0.startDate == $1.startDate {
                return ($0.title ?? "") < ($1.title ?? "")
            }
            return $0.startDate < $1.startDate
        }
        .map { event in
            CalendarEventRecord(
                calendar_name: event.calendar.title,
                title: event.title ?? "Untitled event",
                location: event.location ?? "",
                start_at: formatter.string(from: event.startDate),
                end_at: formatter.string(from: event.endDate),
                all_day: event.isAllDay
            )
        }

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.withoutEscapingSlashes]
    let data = try encoder.encode(records)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    fail(error)
}
