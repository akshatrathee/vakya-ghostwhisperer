# Vakya iOS build helpers
# Requires: Xcode 15+, xcodegen, briefcase, Python 3.11

.PHONY: gen build run testflight clean whisper-coreml phi3-convert

## Generate Xcode project from project.yml (run after any project.yml change)
gen:
	xcodegen generate

## Build debug IPA for simulator
build:
	xcodebuild \
	  -project Vakya.xcodeproj \
	  -scheme Vakya \
	  -destination 'platform=iOS Simulator,name=iPhone 15' \
	  -configuration Debug \
	  build

## Build and run on connected device
run:
	xcodebuild \
	  -project Vakya.xcodeproj \
	  -scheme Vakya \
	  -destination 'platform=iOS,id=$(DEVICE_ID)' \
	  -configuration Debug \
	  build

## Build release archive for TestFlight
testflight:
	xcodebuild \
	  -project Vakya.xcodeproj \
	  -scheme Vakya \
	  -archivePath build/Vakya.xcarchive \
	  archive
	xcodebuild \
	  -exportArchive \
	  -archivePath build/Vakya.xcarchive \
	  -exportOptionsPlist Resources/ExportOptions.plist \
	  -exportPath build/

## Build whisper.cpp with CoreML backend (run once on Mac, copy dylib to Frameworks/)
whisper-coreml:
	git clone https://github.com/ggerganov/whisper.cpp.git /tmp/whisper.cpp
	cd /tmp/whisper.cpp && \
	  bash models/download-ggml-model.sh base.en && \
	  python3 models/generate-coreml-model.py base.en && \
	  make -j WHISPER_COREML=1 && \
	  cp libwhisper.a $(CURDIR)/Frameworks/
	@echo "Copy generated models/whisper-base-en-encoder.mlpackage to Resources/"

## Convert Phi-3 Mini to CoreML (requires coremltools, ~20 min)
phi3-convert:
	python3 ../../scripts/convert_phi3_coreml.py \
	  --model microsoft/Phi-3-mini-4k-instruct \
	  --output ../../models/llm/phi3-mini-q4.mlpackage

clean:
	rm -rf build/ Vakya.xcodeproj DerivedData/
