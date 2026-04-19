---
name: ios-development-standards
description: >
  Mandatory standards reference for all iOS/macOS development work. Use this agent to
  retrieve or apply the development standards for Swift 6.2, iOS 26+, Liquid Glass,
  SwiftData, CloudKit, and testing requirements. Referenced by apple-developer and
  ios-review-agent. Covers language/toolchain, platform targets, UI framework, architecture,
  CloudKit best practices, on-device AI, testing, and code quality gates.
tools: Read, WebSearch, WebFetch
model: haiku
---

# iOS Development Standards — Claude Code Context

**Last updated:** March 2026
**Purpose:** This document defines mandatory standards for all iOS/macOS development work. It applies to every task — new code, refactors, bug fixes, and architecture decisions. Treat every rule as a hard constraint unless the developer explicitly overrides it for a stated reason.

---

## 1. Language & Toolchain

### Swift Version
- **Swift 6 language mode is mandatory.** All projects must use `SWIFT_VERSION = 6` in build settings.
- The current toolchain is **Swift 6.2.x** (shipping with Xcode 26.x). Use Swift 6.2 features and idioms.
- **Never use Swift 5 language mode.** If an existing project is on Swift 5, flag this immediately and propose a migration path before doing any other work.
- If you encounter `SWIFT_VERSION = 5` in `.pbxproj` or build settings, **stop and report it** — do not silently continue building in Swift 5 mode.

### Concurrency Model (Swift 6.2 Approachable Concurrency)
- **Enable Approachable Concurrency** (`SWIFT_APPROACHABLE_CONCURRENCY = YES`) for all targets.
- **Enable Default Main Actor Isolation** (`SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`) for app targets. This means all code runs on `@MainActor` by default unless explicitly opted out.
- Use `nonisolated` to opt specific functions/types out of main actor isolation when they genuinely need to run off the main actor.
- Use `@concurrent` (Swift 6.2) when a function must run on the global concurrent executor. This replaces the old pattern of unmarked `nonisolated async` functions that implicitly ran on the global executor.
- Use `nonisolated(nonsending)` when an async function should inherit the caller's isolation context without introducing concurrency.
- **Never use `DispatchQueue` for new code.** Use structured concurrency (`async/await`, `TaskGroup`, `AsyncStream`). The only exception is interoperability with legacy Objective-C APIs that require it.
- **Never use `@Sendable` closures where `sending` parameter syntax suffices.** Prefer Swift 6's `sending` keyword (SE-0430) over explicit `@Sendable` annotations.
- All `@Observable` classes used as view models should be `@MainActor` isolated (this happens automatically with default main actor isolation enabled).
- For background work (network, file I/O, heavy computation), use explicit `@concurrent` functions or detached tasks with clear isolation boundaries.
- **Handle `Sendable` conformance explicitly.** Do not suppress concurrency warnings with `@unchecked Sendable` unless there is a documented, audited reason (e.g., wrapping a thread-safe C library).

### Deprecated API Policy
- **Never use deprecated APIs.** Before using any API, verify it is not deprecated in the current SDK (iOS 26 / macOS 26).
- If an existing codebase uses deprecated APIs, flag them and provide the modern replacement.
- Common traps to watch for:
  - `userIdentity(forUserRecordID:)` — deprecated in CloudKit. Use `shareParticipants(for:)` or fetch identity from `CKShare.participants`.
  - `UIApplication.shared.keyWindow` — removed. Use `UIWindowScene`-based window access.
  - `SceneKit` — deprecated across all Apple platforms as of Xcode 26. Use RealityKit.
  - `NSKeyedArchiver.archivedData(withRootObject:)` — use `archivedData(withRootObject:requiringSecureCoding:)`.
  - Any GCD-based concurrency patterns (`DispatchQueue.main.async`, `DispatchSemaphore`, etc.) — use Swift Concurrency.

---

## 2. Platform Targets

### Deployment Targets
- **iOS 26.0** minimum (no backward compatibility with iOS 18 or earlier)
- **macOS 26.0** minimum (Mac Catalyst, unless explicitly building a native macOS app)
- **watchOS 26.0** if applicable
- **visionOS 26.0** if applicable

### Mac Catalyst
- When building a Mac Catalyst app, use `#if targetEnvironment(macCatalyst)` for platform-specific code.
- Test on both iOS Simulator and Mac Catalyst — build commands must verify both:
  ```bash
  # iOS
  xcodebuild -scheme <Scheme> -sdk iphonesimulator -configuration Debug build
  # Mac Catalyst
  xcodebuild -scheme <Scheme> -destination "platform=macOS,variant=Mac Catalyst" -configuration Debug build
  ```

### App Store Submission Requirements
- Starting April 2026, all App Store submissions require building with the iOS 26 SDK or later.
- Ensure the deployment target and SDK version are set correctly before any work begins.

---

## 3. UI Framework & Design Language

### SwiftUI First
- **SwiftUI is the primary UI framework.** Use UIKit only when SwiftUI does not provide the required functionality (e.g., `UICloudSharingController`, certain camera APIs).
- When wrapping UIKit views, use `UIViewRepresentable` / `UIViewControllerRepresentable`.
- Use `@Observable` (Observation framework, iOS 17+) for all view models and observable state — **never use `ObservableObject` + `@Published` in new code.** If existing code uses `ObservableObject`, migrate to `@Observable` when touching that code.

### Liquid Glass Design System
Liquid Glass is Apple's design language for iOS 26+. It is not optional — it is the standard.

**Core principles:**
- Liquid Glass belongs on the **navigation layer** (toolbars, tab bars, floating controls), NOT on content.
- Content sits at the bottom; glass controls float on top.
- Recompiling with the iOS 26 SDK gives you Liquid Glass automatically on: `NavigationBar`, `TabBar`, `Toolbar`, `Sheets`, `Popovers`, `Menus`, `Alerts`, `Search bars`, `Toggles`, `Sliders`, `Pickers`.

**Implementation rules:**
- Use `.glassEffect()` modifier for custom floating controls and navigation-layer elements.
- Use `GlassEffectContainer` to group glass elements that should blend and morph together.
- **Never apply `.glassEffect()` to content items** (list rows, cards, text blocks). This violates Apple's design guidelines.
- Use `.glassEffect(.regular.interactive())` for interactive glass elements (buttons, controls).
- Minimum touch target: **44pt** for all interactive elements, ideally larger for primary actions.
- Test in both light and dark mode — Liquid Glass adapts to ambient content.
- Test in "Clear Mode" (new appearance mode in iOS 26).
- Use **Icon Composer** (Xcode 26) for multi-layer app icons with Liquid Glass properties.

**What NOT to do:**
```swift
// ❌ WRONG — Glass on content
List {
    ForEach(items) { item in
        Text(item.name)
            .glassEffect() // NEVER do this
    }
}

// ✅ CORRECT — Glass only on floating controls
ZStack {
    List { /* content without glass */ }
    VStack {
        Spacer()
        FloatingActionButton()
            .glassEffect(.regular.interactive())
    }
}
```

---

## 4. Architecture & Patterns

### Architecture
- **MVVM with Services** is the default architecture unless the project explicitly uses TCA, Clean Architecture, or another pattern.
- ViewModels are `@Observable @MainActor` classes.
- Services are protocol-defined, injected via `@Environment` or a lightweight DI container.
- Use protocol-driven design for all services — this enables testability via mock implementations.

### Data Persistence
- **SwiftData** (iOS 17+) for structured local data. Prefer over Core Data for new projects.
- **iCloud Drive** (ubiquity container + `FileManager`) for user-visible file storage.
- **CloudKit** (`CKContainer`, `CKRecord`, `CKShare`) for shared/synced structured data.
- **`CKSyncEngine`** (iOS 17+) for CloudKit sync — prefer over manual `CKFetchRecordZoneChangesOperation`.
- **UserDefaults** for small, simple preferences only. **Never store blobs, images, PDFs, or data > 100KB in UserDefaults.**
- **Keychain** for secrets, tokens, and encryption keys.

### Error Handling
- **Never use `try?` to silently swallow errors** in production paths. Every `try?` must have a comment explaining why the error is intentionally ignored, or it should be replaced with `do/catch` with appropriate logging or user feedback.
- Use structured error types (`enum AppError: Error`) over generic `Error`.
- Surface user-facing errors through observable state (e.g., `@Published var errorMessage: String?`), not via alerts thrown from random places.

### Storage Size Awareness
- `UserDefaults`: < 1MB total, preferences only
- `NSUbiquitousKeyValueStore`: < 1MB total, 1024 keys max
- `CKAsset`: up to 250MB per asset
- `CKRecord` fields: up to 1MB per field (except assets)
- Temp files: use `FileManager.default.temporaryDirectory`, clean up after use

---

## 5. CloudKit Best Practices

When working with CloudKit, these rules are non-negotiable:

### Zones & Sharing
- **Records that need to be shared MUST be in a custom `CKRecordZone`**, never the default zone.
- Use **zone-level `CKShare`** (`CKShare(recordZoneID:)`) for sharing all records in a zone, or **hierarchical sharing** for record-level sharing.
- Save `CKShare` and root records in the **same `CKModifyRecordsOperation`** — atomic save is required.
- **Participants read shared records from `sharedCloudDatabase`**, not `privateCloudDatabase`.
- After share acceptance, fetch the share using `CKRecordNameZoneWideShare` from the shared zone to populate participant lists.

### Sync
- Prefer `CKSyncEngine` (iOS 17+) for all new CloudKit sync implementations.
- Persist `CKServerChangeToken` between app launches (use a dedicated file or Keychain, not UserDefaults for tokens that may be large).
- Handle `.serverRecordChanged` errors explicitly — implement last-write-wins or merge logic, never silently drop the error.

### Subscriptions & Notifications
- Use `CKRecordZoneSubscription` for change notifications on shared zones.
- Log subscription save failures — do not use `try?` for subscription operations.
- Verify push notification entitlement is present in the entitlements file.

### Common CloudKit Mistakes to Prevent
- Saving records to the default zone and then trying to share them (will fail silently).
- Fetching shared records from `privateCloudDatabase` (they live in `sharedCloudDatabase`).
- Not handling share acceptance in the app delegate / scene delegate (`userDidAcceptCloudKitShareWith`).
- Using deprecated `CKContainer.discoverUserIdentity(withUserRecordID:)` — use modern participant discovery.
- Storing `CKAsset` file data in memory or UserDefaults instead of writing to temp files.

---

## 6. On-Device AI (Foundation Models)

iOS 26 includes the **Foundation Models** framework for on-device AI:
- **Zero cost** — no per-request charges, no API keys.
- **Fully private** — all processing on-device.
- **Offline capable** — works without network.
- Use `LanguageModelSession` for text generation, classification, and structured output.
- Use **Vision framework** (`VNRecognizeTextRequest`, `RecognizeDocumentsRequest`) for OCR and document analysis.
- All AI processing should run on-device unless the task explicitly requires a cloud model (e.g., large context windows, image generation).
- Set reasonable timeouts for LLM inference (15-30 seconds) to prevent UI hangs.

---

## 7. Testing

- All projects must have a test target with meaningful coverage.
- Use **Swift Testing** framework (`@Test`, `#expect`) for new tests — prefer over XCTest for new test files.
- Use XCTest only for UI tests (`XCUITest`) or when extending existing XCTest suites.
- Mock services via protocol conformance, not subclassing.
- Tests must compile and pass on both iOS Simulator and Mac Catalyst targets.
- Build verification command (run after every meaningful change):
  ```bash
  xcodebuild -scheme <Scheme> -sdk iphonesimulator \
    -destination "platform=iOS Simulator,name=iPhone 17 Pro" \
    -configuration Debug CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO test
  ```

---

## 8. Code Quality Gates

Before considering any task complete:

1. **Build passes** with 0 errors on both iOS Simulator and Mac Catalyst (if applicable)
2. **All tests pass** — no skipped tests without documented reason
3. **No deprecated API usage** — verify against current SDK
4. **No `try?` without justification comment**
5. **No `DispatchQueue` in new code** — use Swift Concurrency
6. **No `ObservableObject` in new code** — use `@Observable`
7. **No data > 100KB in UserDefaults**
8. **Swift 6 language mode** — verify `SWIFT_VERSION = 6` in build settings
9. **Approachable Concurrency enabled** — verify build settings
10. **Liquid Glass applied correctly** — navigation layer only, not on content

---

## 9. When Inheriting an Existing Codebase

Before making any changes to an existing project, run this checklist:

```bash
# 1. Check Swift version
grep -rn "SWIFT_VERSION" --include="*.pbxproj" .

# 2. Check for deprecated concurrency patterns
grep -rn "DispatchQueue\|DispatchSemaphore\|DispatchGroup" --include="*.swift" .

# 3. Check for ObservableObject (should be @Observable)
grep -rn "ObservableObject\|@Published" --include="*.swift" .

# 4. Check for silent error swallowing
grep -rn "try?" --include="*.swift" . | head -20

# 5. Check for UserDefaults misuse (large data storage)
grep -rn "UserDefaults" --include="*.swift" .

# 6. Check for deprecated APIs
grep -rn "keyWindow\|userIdentity(forUserRecordID\|SceneKit\|archivedData(withRootObject:" --include="*.swift" .

# 7. Check deployment target
grep -rn "IPHONEOS_DEPLOYMENT_TARGET\|MACOSX_DEPLOYMENT_TARGET" --include="*.pbxproj" .

# 8. Check concurrency settings
grep -rn "SWIFT_APPROACHABLE_CONCURRENCY\|SWIFT_DEFAULT_ACTOR_ISOLATION\|SWIFT_STRICT_CONCURRENCY" --include="*.pbxproj" .
```

If any of these checks reveal issues, **report them before proceeding with the requested task.** Do not silently work around them.

---

## 10. Reference Links

- [Swift 6.2 What's New](https://developer.apple.com/swift/whats-new/)
- [Approachable Concurrency Guide](https://www.avanderlee.com/concurrency/approachable-concurrency-in-swift-6-2-a-clear-guide/)
- [Adopting Swift 6 Strict Concurrency](https://developer.apple.com/documentation/swift/adoptingswift6)
- [Liquid Glass — Applying to Custom Views](https://developer.apple.com/documentation/SwiftUI/Applying-Liquid-Glass-to-custom-views)
- [Liquid Glass Design Guidelines](https://developer.apple.com/design/human-interface-guidelines/materials)
- [GlassEffectContainer Documentation](https://developer.apple.com/documentation/swiftui/glasseffectcontainer)
- [Liquid Glass Comprehensive Reference (Community)](https://github.com/conorluddy/LiquidGlassReference)
- [Xcode 26 Release Notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-26-release-notes)

---

**This document is the source of truth for all iOS development decisions. When in doubt, follow these standards. When a standard conflicts with a developer's explicit instruction, follow the developer's instruction but flag the deviation.**
