import Foundation
import Darwin

struct JarvisSocketTransport {
    let socketPath: String

    func send(requestData: Data) throws -> Data {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else {
            throw BridgeError.processFailed("socket transport failed: socket()")
        }
        defer { close(fd) }

        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)

        let pathBytes = Array(socketPath.utf8)
        let maxLen = MemoryLayout.size(ofValue: address.sun_path)
        guard pathBytes.count < maxLen else {
            throw BridgeError.processFailed("socket path too long: \(socketPath)")
        }

        withUnsafeMutablePointer(to: &address.sun_path) { pathPtr in
            let rawPtr = UnsafeMutableRawPointer(pathPtr).assumingMemoryBound(to: CChar.self)
            rawPtr.initialize(repeating: 0, count: maxLen)
            for (index, byte) in pathBytes.enumerated() {
                rawPtr[index] = CChar(bitPattern: byte)
            }
        }

        let addrLen = socklen_t(MemoryLayout<sa_family_t>.size + pathBytes.count + 1)
        let connectResult = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(fd, $0, addrLen)
            }
        }
        guard connectResult == 0 else {
            throw BridgeError.processFailed("socket transport failed: connect(\(socketPath)) errno=\(errno)")
        }

        try writeAll(fd: fd, data: requestData)
        try writeAll(fd: fd, data: Data([0x0A]))
        shutdown(fd, SHUT_WR)

        return try readUntilNewline(fd: fd)
    }

    private func writeAll(fd: Int32, data: Data) throws {
        try data.withUnsafeBytes { rawBuffer in
            guard let base = rawBuffer.baseAddress else { return }
            var offset = 0
            while offset < rawBuffer.count {
                let written = Darwin.write(fd, base.advanced(by: offset), rawBuffer.count - offset)
                if written < 0 {
                    throw BridgeError.processFailed("socket transport failed: write errno=\(errno)")
                }
                offset += written
            }
        }
    }

    private func readUntilNewline(fd: Int32) throws -> Data {
        var result = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = Darwin.read(fd, &buffer, buffer.count)
            if count < 0 {
                throw BridgeError.processFailed("socket transport failed: read errno=\(errno)")
            }
            if count == 0 {
                break
            }
            result.append(buffer, count: count)
            if result.contains(0x0A) {
                break
            }
        }
        return result
    }
}
