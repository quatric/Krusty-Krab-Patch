// Dev-time: print "<window id> <width> <height>" for every window owned by the given process id.
import CoreGraphics
import Foundation
let pid = Int32(CommandLine.arguments[1])!
let list = CGWindowListCopyWindowInfo(.optionAll, kCGNullWindowID) as! [[String: Any]]
for w in list where (w[kCGWindowOwnerPID as String] as? Int32) == pid {
    let b = w[kCGWindowBounds as String] as! [String: Any]
    print(w[kCGWindowNumber as String] as! Int, b["Width"] as! Double, b["Height"] as! Double)
}
