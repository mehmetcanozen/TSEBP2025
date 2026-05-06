#include <jni.h>

#include <android/log.h>
#include <oboe/Oboe.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace {

constexpr const char *kTag = "NativeOboeAudioEngine";

#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, kTag, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, kTag, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, kTag, __VA_ARGS__)

int nextPowerOfTwo(int value) {
  int result = 1;
  while (result < value) {
    result <<= 1;
  }
  return result;
}

class SpscFloatRing {
 public:
  explicit SpscFloatRing(int requestedCapacity)
      : capacity_(nextPowerOfTwo(std::max(1024, requestedCapacity))),
        mask_(capacity_ - 1),
        buffer_(static_cast<size_t>(capacity_), 0.0f) {}

  int write(const float *source, int count) {
    if (source == nullptr || count <= 0) {
      return 0;
    }
    const int64_t read = readIndex_.load(std::memory_order_acquire);
    const int64_t write = writeIndex_.load(std::memory_order_relaxed);
    const int writable = capacity_ - static_cast<int>(write - read) - 1;
    const int toWrite = std::min(count, std::max(0, writable));
    for (int index = 0; index < toWrite; ++index) {
      buffer_[static_cast<size_t>((write + index) & mask_)] = source[index];
    }
    if (toWrite > 0) {
      writeIndex_.store(write + toWrite, std::memory_order_release);
    }
    return toWrite;
  }

  bool writeOne(float sample) {
    const int64_t read = readIndex_.load(std::memory_order_acquire);
    const int64_t write = writeIndex_.load(std::memory_order_relaxed);
    if (capacity_ - static_cast<int>(write - read) - 1 <= 0) {
      return false;
    }
    buffer_[static_cast<size_t>(write & mask_)] = sample;
    writeIndex_.store(write + 1, std::memory_order_release);
    return true;
  }

  int read(float *destination, int count) {
    if (destination == nullptr || count <= 0) {
      return 0;
    }
    const int64_t read = readIndex_.load(std::memory_order_relaxed);
    const int64_t write = writeIndex_.load(std::memory_order_acquire);
    const int available = static_cast<int>(write - read);
    const int toRead = std::min(count, std::max(0, available));
    for (int index = 0; index < toRead; ++index) {
      destination[index] = buffer_[static_cast<size_t>((read + index) & mask_)];
    }
    if (toRead > 0) {
      readIndex_.store(read + toRead, std::memory_order_release);
    }
    return toRead;
  }

  bool readOne(float *sample) {
    const int64_t read = readIndex_.load(std::memory_order_relaxed);
    const int64_t write = writeIndex_.load(std::memory_order_acquire);
    if (write <= read) {
      return false;
    }
    *sample = buffer_[static_cast<size_t>(read & mask_)];
    readIndex_.store(read + 1, std::memory_order_release);
    return true;
  }

  int availableToRead() const {
    return static_cast<int>(
        writeIndex_.load(std::memory_order_acquire) -
        readIndex_.load(std::memory_order_acquire));
  }

  int dropOldest(int count) {
    if (count <= 0) {
      return 0;
    }
    const int64_t read = readIndex_.load(std::memory_order_relaxed);
    const int64_t write = writeIndex_.load(std::memory_order_acquire);
    const int available = static_cast<int>(write - read);
    const int dropped = std::min(count, std::max(0, available));
    if (dropped > 0) {
      readIndex_.store(read + dropped, std::memory_order_release);
    }
    return dropped;
  }

 private:
  const int capacity_;
  const int mask_;
  std::vector<float> buffer_;
  std::atomic<int64_t> readIndex_{0};
  std::atomic<int64_t> writeIndex_{0};
};

class NativeOboeAudioEngine : public oboe::AudioStreamCallback {
 public:
  NativeOboeAudioEngine(
      int requestedSampleRate,
      int requestedFramesPerBurst,
      int captureCapacityFrames,
      int renderCapacityFrames)
      : requestedSampleRate_(std::max(8000, requestedSampleRate)),
        requestedFramesPerBurst_(std::max(64, requestedFramesPerBurst)),
        captureRing_(captureCapacityFrames),
        renderRing_(renderCapacityFrames) {}

  ~NativeOboeAudioEngine() override {
    stop();
  }

  bool start() {
    if (started_.load(std::memory_order_acquire)) {
      return true;
    }

    auto outputResult = openOutputStream(oboe::SharingMode::Exclusive);
    if (outputResult != oboe::Result::OK) {
      LOGW("Exclusive output open failed: %s; retrying shared",
           oboe::convertToText(outputResult));
      outputResult = openOutputStream(oboe::SharingMode::Shared);
    }
    if (outputResult != oboe::Result::OK) {
      lastError_ = std::string("Output stream open failed: ") +
                   oboe::convertToText(outputResult);
      LOGE("%s", lastError_.c_str());
      stop();
      return false;
    }

    auto inputResult = openInputStream(
        oboe::InputPreset::Unprocessed,
        oboe::SharingMode::Exclusive);
    if (inputResult != oboe::Result::OK) {
      LOGW("Unprocessed exclusive input open failed: %s; retrying voice-recognition shared",
           oboe::convertToText(inputResult));
      inputResult = openInputStream(
          oboe::InputPreset::VoiceRecognition,
          oboe::SharingMode::Shared);
    }
    if (inputResult != oboe::Result::OK) {
      LOGW("Voice-recognition input open failed: %s; retrying generic shared",
           oboe::convertToText(inputResult));
      inputResult = openInputStream(
          oboe::InputPreset::Generic,
          oboe::SharingMode::Shared);
    }
    if (inputResult != oboe::Result::OK) {
      lastError_ = std::string("Input stream open failed: ") +
                   oboe::convertToText(inputResult);
      LOGE("%s", lastError_.c_str());
      stop();
      return false;
    }

    actualSampleRate_.store(outputStream_->getSampleRate(), std::memory_order_release);
    framesPerBurst_.store(std::max(1, outputStream_->getFramesPerBurst()), std::memory_order_release);
    outputChannelCount_.store(std::max(1, outputStream_->getChannelCount()), std::memory_order_release);
    inputChannelCount_.store(std::max(1, inputStream_->getChannelCount()), std::memory_order_release);

    auto startInput = inputStream_->requestStart();
    auto startOutput = outputStream_->requestStart();
    if (startInput != oboe::Result::OK || startOutput != oboe::Result::OK) {
      lastError_ = std::string("Stream start failed: input=") +
                   oboe::convertToText(startInput) + " output=" +
                   oboe::convertToText(startOutput);
      LOGE("%s", lastError_.c_str());
      stop();
      return false;
    }

    started_.store(true, std::memory_order_release);
    LOGD("Started Oboe audio engine sampleRate=%d framesPerBurst=%d inCh=%d outCh=%d",
         actualSampleRate_.load(), framesPerBurst_.load(),
         inputChannelCount_.load(), outputChannelCount_.load());
    return true;
  }

  void stop() {
    started_.store(false, std::memory_order_release);
    closeStream(inputStream_);
    closeStream(outputStream_);
  }

  int readCapture(float *destination, int count) {
    return captureRing_.read(destination, count);
  }

  int writeRender(const float *source, int count) {
    const int written = renderRing_.write(source, count);
    if (written < count) {
      renderOverflows_.fetch_add(1, std::memory_order_relaxed);
    }
    return written;
  }

  int availableCapture() const {
    return captureRing_.availableToRead();
  }

  int availableRender() const {
    return renderRing_.availableToRead();
  }

  int dropOldestRender(int count) {
    return renderRing_.dropOldest(count);
  }

  int actualSampleRate() const {
    return actualSampleRate_.load(std::memory_order_acquire);
  }

  int framesPerBurst() const {
    return framesPerBurst_.load(std::memory_order_acquire);
  }

  int inputChannelCount() const {
    return inputChannelCount_.load(std::memory_order_acquire);
  }

  int outputChannelCount() const {
    return outputChannelCount_.load(std::memory_order_acquire);
  }

  int64_t callbackUnderruns() const {
    return callbackUnderruns_.load(std::memory_order_acquire);
  }

  int64_t inputOverflows() const {
    return inputOverflows_.load(std::memory_order_acquire);
  }

  int64_t renderUnderruns() const {
    return renderUnderruns_.load(std::memory_order_acquire);
  }

  int64_t renderOverflows() const {
    return renderOverflows_.load(std::memory_order_acquire);
  }

  int64_t capturedFrames() const {
    return capturedFrames_.load(std::memory_order_acquire);
  }

  int64_t renderedFrames() const {
    return renderedFrames_.load(std::memory_order_acquire);
  }

  const std::string &lastError() const {
    return lastError_;
  }

  oboe::DataCallbackResult onAudioReady(
      oboe::AudioStream *audioStream,
      void *audioData,
      int32_t numFrames) override {
    if (audioStream == nullptr || audioData == nullptr || numFrames <= 0) {
      return oboe::DataCallbackResult::Continue;
    }

    if (audioStream->getDirection() == oboe::Direction::Input) {
      handleInput(audioStream, static_cast<float *>(audioData), numFrames);
      return oboe::DataCallbackResult::Continue;
    }

    handleOutput(audioStream, static_cast<float *>(audioData), numFrames);
    return oboe::DataCallbackResult::Continue;
  }

  void onErrorAfterClose(oboe::AudioStream *audioStream, oboe::Result error) override {
    (void)audioStream;
    callbackUnderruns_.fetch_add(1, std::memory_order_relaxed);
    LOGW("Oboe stream closed after error: %s", oboe::convertToText(error));
  }

 private:
  static void closeStream(std::shared_ptr<oboe::AudioStream> &stream) {
    if (!stream) {
      return;
    }
    stream->requestStop();
    stream->close();
    stream.reset();
  }

  oboe::Result openOutputStream(oboe::SharingMode sharingMode) {
    oboe::AudioStreamBuilder builder;
    builder.setDirection(oboe::Direction::Output)
        ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
        ->setSharingMode(sharingMode)
        ->setSampleRate(requestedSampleRate_)
        ->setFramesPerCallback(requestedFramesPerBurst_)
        ->setChannelCount(oboe::ChannelCount::Mono)
        ->setFormat(oboe::AudioFormat::Float)
        ->setUsage(oboe::Usage::Media)
        ->setContentType(oboe::ContentType::Music)
        ->setCallback(this);
    return builder.openStream(outputStream_);
  }

  oboe::Result openInputStream(
      oboe::InputPreset inputPreset,
      oboe::SharingMode sharingMode) {
    oboe::AudioStreamBuilder builder;
    builder.setDirection(oboe::Direction::Input)
        ->setPerformanceMode(oboe::PerformanceMode::LowLatency)
        ->setSharingMode(sharingMode)
        ->setSampleRate(requestedSampleRate_)
        ->setFramesPerCallback(requestedFramesPerBurst_)
        ->setChannelCount(oboe::ChannelCount::Mono)
        ->setFormat(oboe::AudioFormat::Float)
        ->setInputPreset(inputPreset)
        ->setCallback(this);
    return builder.openStream(inputStream_);
  }

  void handleInput(
      oboe::AudioStream *stream,
      const float *audioData,
      int32_t numFrames) {
    const int channels = std::max(1, stream->getChannelCount());
    if (channels == 1) {
      const int written = captureRing_.write(audioData, numFrames);
      if (written < numFrames) {
        inputOverflows_.fetch_add(1, std::memory_order_relaxed);
      }
    } else {
      int written = 0;
      for (int32_t frame = 0; frame < numFrames; ++frame) {
        double value = 0.0;
        for (int channel = 0; channel < channels; ++channel) {
          value += audioData[frame * channels + channel];
        }
        if (captureRing_.writeOne(static_cast<float>(value / static_cast<double>(channels)))) {
          ++written;
        }
      }
      if (written < numFrames) {
        inputOverflows_.fetch_add(1, std::memory_order_relaxed);
      }
    }
    capturedFrames_.fetch_add(numFrames, std::memory_order_relaxed);
  }

  void handleOutput(
      oboe::AudioStream *stream,
      float *audioData,
      int32_t numFrames) {
    const int channels = std::max(1, stream->getChannelCount());
    bool callbackUnderrun = false;
    for (int32_t frame = 0; frame < numFrames; ++frame) {
      float sample = 0.0f;
      if (renderRing_.readOne(&sample)) {
        lastOutputSample_ = std::clamp(sample, -0.98f, 0.98f);
      } else {
        callbackUnderrun = true;
        lastOutputSample_ *= 0.985f;
      }
      for (int channel = 0; channel < channels; ++channel) {
        audioData[frame * channels + channel] = lastOutputSample_;
      }
    }
    if (callbackUnderrun) {
      callbackUnderruns_.fetch_add(1, std::memory_order_relaxed);
      renderUnderruns_.fetch_add(1, std::memory_order_relaxed);
    }
    renderedFrames_.fetch_add(numFrames, std::memory_order_relaxed);
  }

  const int requestedSampleRate_;
  const int requestedFramesPerBurst_;
  SpscFloatRing captureRing_;
  SpscFloatRing renderRing_;
  std::shared_ptr<oboe::AudioStream> inputStream_;
  std::shared_ptr<oboe::AudioStream> outputStream_;
  std::atomic<bool> started_{false};
  std::atomic<int> actualSampleRate_{0};
  std::atomic<int> framesPerBurst_{0};
  std::atomic<int> inputChannelCount_{0};
  std::atomic<int> outputChannelCount_{0};
  std::atomic<int64_t> callbackUnderruns_{0};
  std::atomic<int64_t> inputOverflows_{0};
  std::atomic<int64_t> renderUnderruns_{0};
  std::atomic<int64_t> renderOverflows_{0};
  std::atomic<int64_t> capturedFrames_{0};
  std::atomic<int64_t> renderedFrames_{0};
  float lastOutputSample_ = 0.0f;
  std::string lastError_;
};

NativeOboeAudioEngine *fromHandle(jlong handle) {
  return reinterpret_cast<NativeOboeAudioEngine *>(handle);
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeCreate(
    JNIEnv *env,
    jobject /* thiz */,
    jint requestedSampleRate,
    jint requestedFramesPerBurst,
    jint captureCapacityFrames,
    jint renderCapacityFrames) {
  (void)env;
  auto *engine = new NativeOboeAudioEngine(
      requestedSampleRate,
      requestedFramesPerBurst,
      captureCapacityFrames,
      renderCapacityFrames);
  return reinterpret_cast<jlong>(engine);
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeStart(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle) {
  (void)env;
  auto *engine = fromHandle(handle);
  return engine != nullptr && engine->start();
}

extern "C" JNIEXPORT void JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeStop(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle) {
  (void)env;
  auto *engine = fromHandle(handle);
  if (engine != nullptr) {
    engine->stop();
  }
}

extern "C" JNIEXPORT void JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeRelease(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle) {
  (void)env;
  delete fromHandle(handle);
}

extern "C" JNIEXPORT jint JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeReadCapture(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle,
    jfloatArray destination,
    jint maxFrames) {
  auto *engine = fromHandle(handle);
  if (engine == nullptr || destination == nullptr || maxFrames <= 0) {
    return 0;
  }
  const jsize length = env->GetArrayLength(destination);
  const int count = std::min(static_cast<int>(length), static_cast<int>(maxFrames));
  jfloat *data = env->GetFloatArrayElements(destination, nullptr);
  const int read = engine->readCapture(data, count);
  env->ReleaseFloatArrayElements(destination, data, 0);
  return read;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeWriteRender(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle,
    jfloatArray source,
    jint frames) {
  auto *engine = fromHandle(handle);
  if (engine == nullptr || source == nullptr || frames <= 0) {
    return 0;
  }
  const jsize length = env->GetArrayLength(source);
  const int count = std::min(static_cast<int>(length), static_cast<int>(frames));
  jfloat *data = env->GetFloatArrayElements(source, nullptr);
  const int written = engine->writeRender(data, count);
  env->ReleaseFloatArrayElements(source, data, JNI_ABORT);
  return written;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeAvailableCapture(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle) {
  (void)env;
  auto *engine = fromHandle(handle);
  return engine == nullptr ? 0 : engine->availableCapture();
}

extern "C" JNIEXPORT jint JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeAvailableRender(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle) {
  (void)env;
  auto *engine = fromHandle(handle);
  return engine == nullptr ? 0 : engine->availableRender();
}

extern "C" JNIEXPORT jint JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeDropOldestRender(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle,
    jint frames) {
  (void)env;
  auto *engine = fromHandle(handle);
  return engine == nullptr ? 0 : engine->dropOldestRender(frames);
}

extern "C" JNIEXPORT jlongArray JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeStats(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle) {
  jlong values[11] = {};
  auto *engine = fromHandle(handle);
  if (engine != nullptr) {
    values[0] = engine->actualSampleRate();
    values[1] = engine->framesPerBurst();
    values[2] = engine->inputChannelCount();
    values[3] = engine->outputChannelCount();
    values[4] = engine->callbackUnderruns();
    values[5] = engine->inputOverflows();
    values[6] = engine->renderUnderruns();
    values[7] = engine->renderOverflows();
    values[8] = engine->capturedFrames();
    values[9] = engine->renderedFrames();
    values[10] = engine->availableRender();
  }
  jlongArray result = env->NewLongArray(11);
  env->SetLongArrayRegion(result, 0, 11, values);
  return result;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_anonymous_mobiletest_suppression_NativeOboeAudioEngine_nativeLastError(
    JNIEnv *env,
    jobject /* thiz */,
    jlong handle) {
  auto *engine = fromHandle(handle);
  const char *message = engine == nullptr ? "Native Oboe engine is not allocated" : engine->lastError().c_str();
  return env->NewStringUTF(message);
}
