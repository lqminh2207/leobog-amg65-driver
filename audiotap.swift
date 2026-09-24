// audiotap: taps the Mac's system audio output (Core Audio process tap, macOS 14.2+) and prints
// 63 log-spaced band levels in 0...1, one line of space-separated values ~30 times per second.
// On failure prints "ERR <message>" and exits non-zero.
import Accelerate
import AudioToolbox
import CoreAudio
import Foundation

let bandCount = 63
let fftSize = 2048
let minFreq: Float = 40, maxFreq: Float = 14000
let floorDb: Float = -72, ceilDb: Float = -12

setvbuf(stdout, nil, _IOLBF, 0)

func fail(_ message: String) -> Never {
    print("ERR \(message)")
    exit(1)
}

func property<T: BitwiseCopyable>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector, _ initial: T) -> T {
    var address = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                                             mElement: kAudioObjectPropertyElementMain)
    var value = initial
    var size = UInt32(MemoryLayout<T>.size)
    let status = AudioObjectGetPropertyData(object, &address, 0, nil, &size, &value)
    if status != noErr { fail("khong doc duoc thuoc tinh am thanh (\(status))") }
    return value
}

// Ring of the latest mono samples, written on the audio thread and read by the analyser
final class SampleRing {
    private var buffer = [Float](repeating: 0, count: fftSize)
    private var index = 0
    private let lock = NSLock()

    func append(_ samples: UnsafePointer<Float>, frames: Int, channels: Int) {
        lock.lock()
        for f in 0..<frames {
            var sum: Float = 0
            for c in 0..<channels { sum += samples[f * channels + c] }
            buffer[index] = sum / Float(channels)
            index = (index + 1) % fftSize
        }
        lock.unlock()
    }

    func snapshot() -> [Float] {
        lock.lock()
        defer { lock.unlock() }
        return Array(buffer[index...] + buffer[..<index])
    }
}

let ring = SampleRing()

// 1. Tap every process's output (nothing excluded), unmuted so the user still hears it
let tapDescription = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
tapDescription.uuid = UUID()
tapDescription.name = "AMG65 LED visualizer"
tapDescription.isPrivate = true
tapDescription.muteBehavior = .unmuted

var tapID = AudioObjectID(kAudioObjectUnknown)
var status = AudioHardwareCreateProcessTap(tapDescription, &tapID)
if status != noErr { fail("khong tao duoc tap am thanh (\(status)) - kiem tra quyen Ghi am thanh he thong") }

// 2. A private aggregate device clocked by the current output device reads the tap
let outputDevice = property(AudioObjectID(kAudioObjectSystemObject),
                            kAudioHardwarePropertyDefaultSystemOutputDevice, AudioObjectID(kAudioObjectUnknown))
var uidAddress = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyDeviceUID,
                                            mScope: kAudioObjectPropertyScopeGlobal,
                                            mElement: kAudioObjectPropertyElementMain)
var uidRef: Unmanaged<CFString>?
var uidSize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
status = AudioObjectGetPropertyData(outputDevice, &uidAddress, 0, nil, &uidSize, &uidRef)
guard status == noErr, let outputUID = uidRef?.takeRetainedValue() as String? else {
    fail("khong doc duoc thiet bi phat am thanh (\(status))")
}
let aggregate: [String: Any] = [
    kAudioAggregateDeviceNameKey: "AMG65 Visualizer Tap",
    kAudioAggregateDeviceUIDKey: UUID().uuidString,
    kAudioAggregateDeviceMainSubDeviceKey: outputUID,
    kAudioAggregateDeviceIsPrivateKey: true,
    kAudioAggregateDeviceIsStackedKey: false,
    kAudioAggregateDeviceTapAutoStartKey: true,
    kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
    kAudioAggregateDeviceTapListKey: [[kAudioSubTapDriftCompensationKey: true,
                                       kAudioSubTapUIDKey: tapDescription.uuid.uuidString]],
]
var aggregateID = AudioObjectID(kAudioObjectUnknown)
status = AudioHardwareCreateAggregateDevice(aggregate as CFDictionary, &aggregateID)
if status != noErr { fail("khong tao duoc thiet bi am thanh tong hop (\(status))") }

let format = property(tapID, kAudioTapPropertyFormat, AudioStreamBasicDescription())
let sampleRate = Float(format.mSampleRate > 0 ? format.mSampleRate : 48000)

var procID: AudioDeviceIOProcID?
status = AudioDeviceCreateIOProcIDWithBlock(&procID, aggregateID, nil) { _, input, _, _, _ in
    for buffer in UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input)) {
        guard let data = buffer.mData else { continue }
        let channels = max(1, Int(buffer.mNumberChannels))
        let frames = Int(buffer.mDataByteSize) / (MemoryLayout<Float>.size * channels)
        ring.append(data.assumingMemoryBound(to: Float.self), frames: frames, channels: channels)
    }
}
if status != noErr { fail("khong gan duoc bo doc am thanh (\(status))") }
status = AudioDeviceStart(aggregateID, procID)
if status != noErr { fail("khong bat dau doc duoc am thanh (\(status))") }

func cleanup() {
    AudioDeviceStop(aggregateID, procID)
    if let procID { AudioDeviceDestroyIOProcID(aggregateID, procID) }
    AudioHardwareDestroyAggregateDevice(aggregateID)
    AudioHardwareDestroyProcessTap(tapID)
}
for sig in [SIGINT, SIGTERM, SIGPIPE] {
    signal(sig) { _ in cleanup(); exit(0) }
}

// 3. FFT -> 63 log-spaced bands -> dB -> 0...1 with fast attack and slow decay
let log2n = vDSP_Length(log2(Float(fftSize)))
guard let fftSetup = vDSP_create_fftsetup(log2n, FFTRadix(kFFTRadix2)) else { fail("FFT setup") }
var window = [Float](repeating: 0, count: fftSize)
vDSP_hann_window(&window, vDSP_Length(fftSize), Int32(vDSP_HANN_NORM))

let binWidth = sampleRate / Float(fftSize)
let bandBins: [(Int, Int)] = (0..<bandCount).map { band in
    let lo = minFreq * pow(maxFreq / minFreq, Float(band) / Float(bandCount))
    let hi = minFreq * pow(maxFreq / minFreq, Float(band + 1) / Float(bandCount))
    let a = max(1, Int(lo / binWidth))
    return (a, max(a, min(fftSize / 2 - 1, Int(hi / binWidth))))
}
var levels = [Float](repeating: 0, count: bandCount)

Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { _ in
    var samples = ring.snapshot()
    vDSP_vmul(samples, 1, window, 1, &samples, 1, vDSP_Length(fftSize))
    var real = [Float](repeating: 0, count: fftSize / 2)
    var imag = [Float](repeating: 0, count: fftSize / 2)
    var magnitudes = [Float](repeating: 0, count: fftSize / 2)
    real.withUnsafeMutableBufferPointer { rp in
        imag.withUnsafeMutableBufferPointer { ip in
            var split = DSPSplitComplex(realp: rp.baseAddress!, imagp: ip.baseAddress!)
            samples.withUnsafeBufferPointer { sp in
                sp.baseAddress!.withMemoryRebound(to: DSPComplex.self, capacity: fftSize / 2) {
                    vDSP_ctoz($0, 2, &split, 1, vDSP_Length(fftSize / 2))
                }
            }
            vDSP_fft_zrip(fftSetup, &split, 1, log2n, FFTDirection(FFT_FORWARD))
            vDSP_zvabs(&split, 1, &magnitudes, 1, vDSP_Length(fftSize / 2))
        }
    }
    var line = ""
    for (band, (lo, hi)) in bandBins.enumerated() {
        let peak = magnitudes[lo...hi].max() ?? 0
        let db = 20 * log10(peak / Float(fftSize) + 1e-9)
        let target = min(1, max(0, (db - floorDb) / (ceilDb - floorDb)))
        levels[band] = target > levels[band] ? target : levels[band] * 0.82 + target * 0.18
        line += String(format: band == 0 ? "%.2f" : " %.2f", levels[band])
    }
    print(line)
}
RunLoop.main.run()
