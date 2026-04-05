BINARY := .build/arm64-apple-macosx/debug/JarvisMenuBar
APP_BUNDLE := .build/JarvisMenuBar.app
APP_BINARY := $(APP_BUNDLE)/Contents/MacOS/JarvisMenuBar

.PHONY: build run clean

build:
	swift build
	@mkdir -p $(APP_BUNDLE)/Contents/MacOS
	@cp $(BINARY) $(APP_BINARY)
	@cp Resources/Info.plist $(APP_BUNDLE)/Contents/Info.plist
	@codesign --force --sign - --entitlements Resources/JarvisMenuBar.entitlements $(APP_BUNDLE)
	@echo "✓ Built and signed: $(APP_BUNDLE)"

run: build
	open $(APP_BUNDLE)

run-log: build
	$(APP_BINARY) 2>&1 | tee /tmp/jarvis_menubar.log

clean:
	swift package clean
	rm -rf $(APP_BUNDLE)
