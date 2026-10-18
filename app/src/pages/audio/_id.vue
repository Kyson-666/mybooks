<template>
  <div class="audio-player-container">
    <!-- 上方区域 60% -->
    <div class="audio-upper-section">
      <!-- 左侧封面区域 -->
      <div class="cover-section">
        <div class="cover-container">
          <v-img
            :src="book.img"
            :aspect-ratio="3/4"
            class="book-cover"
            @click="gotoBookDetail()"
            contain
          ></v-img>
          <div class="book-info">
            <h2 class="book-title">{{ book.title }}</h2>
            <p v-if="shouldShowAuthors" class="book-author">{{ book.authors }}</p>
          </div>
        </div>
      </div>

      <!-- 右侧音频列表 -->
      <div class="playlist-section">
        <div class="playlist-header">
          <h3>{{ $t('audio.playlist') }}</h3>
          <div class="playlist-controls">
            <v-chip v-if="audioFiles.length > 0" small outlined class="chapter-info">
              {{ currentTrackIndex + 1 }}/{{ audioFiles.length }}
            </v-chip>
            <v-btn
              v-if="!isPaid && audioFiles.length > 0"
              small
              color="orange darken-4"
              @click="showPurchaseDialogWithVipInfo"
              class="purchase-btn"
              :loading="purchaseLoading"
            >
              <v-icon small left>mdi-cart</v-icon>
              {{ $t('audio.purchase') }}
            </v-btn>
            <v-btn
              small
              outlined
              @click="downloadCollection"
              class="download-btn"
              :disabled="audioFiles.length === 0 || !isPaid"
              :loading="downloadLoading"
            >
              <v-icon small left>mdi-download</v-icon>
              {{ $t('audio.downloadCollection') }}
            </v-btn>
            <v-btn
              small
              outlined
              @click="closePlayer"
              class="close-btn"
            >
              <v-icon small left>mdi-close</v-icon>
              {{ $t('common.close') }}
            </v-btn>
          </div>
        </div>

        <div class="playlist-container" v-if="audioFiles.length > 0">
          <div
            v-for="(audio, index) in audioFiles"
            :key="index"
            class="playlist-item"
            :class="{
              'active': currentTrackIndex === index,
              'locked': !isPaid && index >= 5
            }"
            @click="selectTrack(index)"
          >
            <div class="track-number">{{ index + 1 }}</div>
            <div class="track-info">
              <div class="track-title">{{ getDisplayName(audio.filename) }}</div>
              <div class="track-duration">{{ formatFileSize(audio.size) }}</div>
            </div>
            <v-chip
              v-if="!isPaid && index >= 5"
              x-small
              color="blue darken-2"
              text-color="yellow"
              class="vip-badge"
            >
              VIP
            </v-chip>
            <v-icon v-else-if="currentTrackIndex === index && isPlaying" color="primary">
              mdi-volume-high
            </v-icon>
          </div>
        </div>

        <!-- 未购买提示信息 -->
        <div v-if="!isPaid && audioFiles.length > 0" class="purchase-hint">
          <v-alert
            type="info"
            outlined
            dense
            class="ma-2"
          >
            {{ $t('audio.purchaseHint') }}
          </v-alert>
        </div>

        <div  v-if="audioFiles.length == 0" class="no-audio-message">
          <v-icon large color="grey">mdi-headphones-off</v-icon>
          <p>{{ $t('audio.noAudioFiles') }}</p>
        </div>
      </div>
    </div>

    <!-- 下方播放控制条 40% -->
    <div class="audio-controls-section">
      <!-- 进度条 -->
      <div class="progress-section">
        <div class="time-display">
          <span>{{ formatTime(currentTime) }}</span>
          <span>{{ formatTime(duration) }}</span>
        </div>
        <v-slider
          v-model="progress"
          :max="100"
          hide-details
          @change="seekTo"
          @mousedown="isDragging = true"
          @mouseup="isDragging = false"
          class="progress-slider"
        ></v-slider>
      </div>

      <!-- 字幕显示区 -->
      <div class="subtitle-section" v-if="showSubtitle && subtitleCues.length">
        <div
          class="subtitle-text"
          @click="currentCue && seekToCue(currentCue)"
          :title="$t('audio.subtitle')"
        >{{ currentCue ? currentCue.text : ' ' }}</div>
      </div>

      <!-- 控制按钮 -->
      <div class="controls-section">
        <div class="main-controls">
          <!-- 上一首 -->
          <v-btn
            icon
            large
            @click="previousTrack"
            :disabled="currentTrackIndex <= 0"
            class="control-btn nav-btn"
          >
            <v-icon>mdi-skip-previous</v-icon>
          </v-btn>

          <!-- 播放/暂停 -->
          <v-btn
            icon
            x-large
            @click="togglePlay"
            :disabled="!currentAudio"
            class="play-btn"
          >
            <v-icon>{{ isPlaying ? 'mdi-pause' : 'mdi-play' }}</v-icon>
          </v-btn>

          <!-- 下一首 -->
          <v-btn
            icon
            large
            @click="nextTrack"
            :disabled="currentTrackIndex >= audioFiles.length - 1"
            class="control-btn nav-btn"
          >
            <v-icon>mdi-skip-next</v-icon>
          </v-btn>
        </div>

        <div class="secondary-controls">
          <!-- 字幕开关 -->
          <v-btn
            v-if="subtitleCues.length > 0"
            icon
            large
            @click="toggleSubtitle"
            class="subtitle-btn"
            :color="showSubtitle ? 'primary' : ''"
          >
            <v-icon>{{ showSubtitle ? 'mdi-subtitles' : 'mdi-subtitles-outline' }}</v-icon>
          </v-btn>

          <!-- 倍速控制 -->
          <v-menu offset-y>
            <template v-slot:activator="{ on, attrs }">
              <v-btn
                icon
                large
                v-bind="attrs"
                v-on="on"
                class="speed-btn"
              >
                <v-icon>mdi-speedometer</v-icon>
                <span class="speed-text">{{ playbackRate }}x</span>
              </v-btn>
            </template>
            <v-list>
              <v-list-item
                v-for="rate in playbackRates"
                :key="rate"
                @click="setPlaybackRate(rate)"
              >
                <v-list-item-title>{{ rate }}x</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>

          <!-- 定时关闭 -->
          <v-menu offset-y>
            <template v-slot:activator="{ on, attrs }">
              <v-btn
                icon
                large
                v-bind="attrs"
                v-on="on"
                class="timer-btn"
                :color="sleepTimer ? 'primary' : ''"
              >
                <v-icon>{{ sleepTimer ? 'mdi-timer' : 'mdi-timer-outline' }}</v-icon>
              </v-btn>
            </template>
            <v-list>
              <v-list-item @click="setSleepTimer(null)">
                <v-list-item-title>{{ $t('audio.timerOff') }}</v-list-item-title>
              </v-list-item>
              <v-list-item
                v-for="timer in sleepTimers"
                :key="timer.value"
                @click="setSleepTimer(timer)"
              >
                <v-list-item-title>{{ timer.label }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
        </div>
        <div>
          <v-btn color="error" @click="openDeleteDialog" class="delete-btn" style="margin-top: 10px;">
            <v-icon>mdi-delete</v-icon>{{ $t('audio.audioDelete') }}
          </v-btn>
        </div>
      </div>
    </div>

    <!-- 隐藏的音频元素 -->
    <audio
      ref="audioPlayer"
      @loadedmetadata="onLoadedMetadata"
      @timeupdate="onTimeUpdate"
      @ended="onTrackEnded"
      @play="onPlay"
      @pause="onPause"
      preload="metadata"
    ></audio>

    <!-- VIP信息对话框 -->
    <AppDialog
      v-model="showVipDialog"
      :persistent="false"
      type="action"
      :title="vipDialogTitle"
      max-width="600px"
      :dismiss-label="$t('common.close')"
      hide-footer-button
    >
      <div v-html="vipDialogContent"></div>
    </AppDialog>

    <!-- 购买确认对话框 -->
    <AppDialog
      v-model="showPurchaseDialog"
      :persistent="false"
      type="confirm"
      :title="$t('audio.confirmPurchase')"
      color="orange darken-4"
      confirm-dark
      max-width="400px"
      :confirm-text="$t('audio.confirmPurchase')"
      :confirm-loading="purchaseLoading"
      @confirm="purchaseAudio"
    >
      <p>{{ $t('audio.purchaseDescription', { title: book.title }) }}</p>
      <p class="price-text">{{ $t('audio.price') }}1个额度</p>
    </AppDialog>

    <!-- 删除确认对话框 -->
    <AppDialog
      v-model="showDeleteDialog"
      :persistent="false"
      type="confirm"
      :title="$t('audio.audioDelete')"
      color="deep-orange"
      confirm-dark
      max-width="400px"
      :confirm-text="$t('common.delete')"
      :confirm-loading="deleteLoading"
      @confirm="deleteAudio"
    >
      <p>{{ $t('audio.deleteDescription', { title: book.title }) }}</p>
    </AppDialog>
  </div>
</template>

<script>
export default {
  async asyncData({ params, app }) {
    const bookId = params.id;

    try {
      // 获取书籍信息
      const bookResponse = await app.$backend(`/book/${bookId}`);
      if (bookResponse.err !== 'ok') {
        throw new Error(bookResponse.msg || '书籍不存在');
      }

      // 获取音频文件列表
      const audioResponse = await app.$backend(`/audio/${bookId}`);

      return {
        book: bookResponse.book,
        audioFiles: audioResponse.audios || [],
        audioStatus: audioResponse.status || 'unavailable',
        bookId: bookId,
        isPaid: audioResponse.is_paid || false
      };
    } catch (error) {
      console.error('Error loading audio data:', error);
      return {
        book: {},
        audioFiles: [],
        audioStatus: 'unavailable',
        bookId: params.id,
        isPaid: false
      };
    }
  },

  head() {
    return {
      title: `${this.book.title || ''} - ${this.$t('audio.audioBook')}`,
      bodyAttrs: {
        class: 'audio-player-page'
      }
    };
  },

  data() {
    return {
      // 播放状态
      isPlaying: false,
      currentTrackIndex: 0,
      currentTime: 0,
      duration: 0,
      progress: 0,
      isDragging: false,

      // 音频设置
      playbackRate: 1,
      playbackRates: [0.5, 1, 1.25, 1.5, 2],

      // 字幕相关
      subtitleCues: [],
      currentCueIndex: -1,
      showSubtitle: true,
      subtitleCache: {},

      // 定时器
      sleepTimer: null,
      sleepTimerInterval: null,
      sleepTimers: [
        { value: 'current', label: this.$t('audio.currentChapter') },
        { value: 15, label: this.$t('audio.timer15min') },
        { value: 30, label: this.$t('audio.timer30min') },
        { value: 60, label: this.$t('audio.timer1hour') }
      ],

      // 播放位置记录
      saveProgressInterval: null,
      bookId: null,

      // 下载相关
      downloadLoading: false,
      showVipDialog: false,
      vipDialogTitle: '',
      vipDialogContent: '',

      // 购买相关
      purchaseLoading: false,
      isPaid: false,
      showPurchaseDialog: false,

      // 删除相关
      deleteLoading: false,
      showDeleteDialog: false
    };
  },

  computed: {
    currentAudio() {
      return this.audioFiles[this.currentTrackIndex];
    },

    currentCue() {
      if (this.currentCueIndex >= 0 && this.currentCueIndex < this.subtitleCues.length) {
        return this.subtitleCues[this.currentCueIndex];
      }
      return null;
    },

    shouldShowAuthors() {
      // 如果作者信息不存在，隐藏
      if (!this.book.authors) {
        return false;
      }

      // 如果作者只有一个元素且是 "Unknown"，隐藏
      if (this.book.authors[0] === 'Unknown') {
        return false;
      }

      return true;
    }
  },

  mounted() {
    this.restoreSubtitlePreference();
    this.initializePlayer();
    this.restorePlaybackPosition();
    this.startProgressSaving();
    this.escKeyListener = (event) => {
      if (event.key === 'Escape' || event.keyCode === 27) {
        this.closePlayer();
      }
    };
    window.addEventListener('keyup', this.escKeyListener);
  },

  beforeDestroy() {
    this.savePlaybackPosition();
    this.clearSleepTimer();
    this.stopProgressSaving();
    if (this.$refs.audioPlayer) {
      this.$refs.audioPlayer.pause();
    }
    window.removeEventListener('keyup', this.escKeyListener);
  },

  methods: {
    initializePlayer() {
      if (this.audioFiles.length > 0) {
        this.loadTrack(0);
      }
    },

    loadTrack(index, initialTime = null) {
      if (index >= 0 && index < this.audioFiles.length) {
        this.currentTrackIndex = index;
        const audio = this.audioFiles[index];
        this.loadSubtitle(audio.subtitle);
        const player = this.$refs.audioPlayer;
        if (!player) return;

        const isSameFile = (player.getAttribute('src') === audio.url || player.src === audio.url) && audio.url;
        const targetTime = (initialTime !== null ? initialTime : 0) + (audio.start_time || 0);

        if (isSameFile) {
          player.currentTime = targetTime;
          if (audio.start_time !== undefined && audio.end_time !== undefined) {
            this.duration = audio.end_time - audio.start_time;
          } else {
            this.duration = player.duration || 0;
          }
        } else {
          player.src = audio.url;
          player.load();
          const onLoadedMetadata = () => {
            player.currentTime = targetTime;
            if (audio.start_time !== undefined && audio.end_time !== undefined) {
              this.duration = audio.end_time - audio.start_time;
            } else {
              this.duration = player.duration || 0;
            }
            player.removeEventListener('loadedmetadata', onLoadedMetadata);
          };
          player.addEventListener('loadedmetadata', onLoadedMetadata);
        }
      }
    },

    selectTrack(index) {
      // 检查是否为付费内容
      if (!this.isPaid && index >= 5) {
        return;
      }

      if (index !== this.currentTrackIndex) {
        // 保存当前播放位置
        this.savePlaybackPosition();

        this.loadTrack(index);
        // 自动开始播放新选择的音频
        this.$nextTick(() => {
          this.$refs.audioPlayer.play();
        });
      } else {
        // 如果点击的是当前正在播放的音频，则切换播放/暂停状态
        this.togglePlay();
      }
    },

    togglePlay() {
      if (!this.$refs.audioPlayer) return;

      if (this.isPlaying) {
        this.$refs.audioPlayer.pause();
      } else {
        this.$refs.audioPlayer.play();
      }
    },

    previousTrack() {
      if (this.currentTrackIndex > 0) {
        // 保存当前播放位置
        this.savePlaybackPosition();

        this.loadTrack(this.currentTrackIndex - 1);
        if (this.isPlaying) {
          this.$nextTick(() => {
            this.$refs.audioPlayer.play();
          });
        }
      }
    },

    nextTrack(forcePlay = false) {
      if (this.currentTrackIndex < this.audioFiles.length - 1) {
        // 保存当前播放位置
        this.savePlaybackPosition();

        this.loadTrack(this.currentTrackIndex + 1);
        if (forcePlay || this.isPlaying) {
          this.$nextTick(() => {
            this.$refs.audioPlayer.play();
          });
        }
      }
    },

    seekTo(value) {
      if (this.$refs.audioPlayer && this.duration > 0) {
        const audio = this.currentAudio;
        let seekTime = (value / 100) * this.duration;
        if (audio && audio.start_time !== undefined) {
          seekTime += audio.start_time;
        }
        this.$refs.audioPlayer.currentTime = seekTime;
      }
    },

    setPlaybackRate(rate) {
      this.playbackRate = rate;
      if (this.$refs.audioPlayer) {
        this.$refs.audioPlayer.playbackRate = rate;
      }
    },

    setSleepTimer(timer) {
      this.clearSleepTimer();
      this.sleepTimer = timer;

      if (timer) {
        if (timer.value === 'current') {
          // 当前章节结束后停止
          this.sleepTimer.type = 'current';
        } else {
          // 定时停止
          this.sleepTimer.type = 'timeout';
          this.sleepTimer.endTime = Date.now() + (timer.value * 60 * 1000);
          this.sleepTimerInterval = setInterval(() => {
            if (Date.now() >= this.sleepTimer.endTime) {
              this.pauseAndClearTimer();
            }
          }, 1000);
        }
      }
    },

    clearSleepTimer() {
      if (this.sleepTimerInterval) {
        clearInterval(this.sleepTimerInterval);
        this.sleepTimerInterval = null;
      }
      this.sleepTimer = null;
    },

    pauseAndClearTimer() {
      this.$refs.audioPlayer.pause();
      this.clearSleepTimer();
    },

    // 音频事件处理
    onLoadedMetadata() {
      const audio = this.currentAudio;
      if (audio && audio.end_time !== undefined && audio.start_time !== undefined) {
        this.duration = audio.end_time - audio.start_time;
      } else {
        this.duration = this.$refs.audioPlayer.duration || 0;
      }
      this.$refs.audioPlayer.playbackRate = this.playbackRate;
    },

    onTimeUpdate() {
      if (!this.isDragging && this.$refs.audioPlayer) {
        const audio = this.currentAudio;
        const playerTime = this.$refs.audioPlayer.currentTime;

        if (audio && audio.end_time !== undefined) {
          if (playerTime >= audio.end_time) {
            this.onTrackEnded();
            return;
          }
          this.currentTime = Math.max(0, playerTime - (audio.start_time || 0));
        } else {
          this.currentTime = playerTime;
        }

        if (this.duration > 0) {
          this.progress = (this.currentTime / this.duration) * 100;
        }

        this.syncSubtitle();
      }
    },

    onTrackEnded() {
      // 保存播放位置
      this.savePlaybackPosition();

      // 检查定时器
      if (this.sleepTimer && this.sleepTimer.type === 'current') {
        this.pauseAndClearTimer();
        return;
      }

      // 自动播放下一首
      if (this.currentTrackIndex < this.audioFiles.length - 1) {
        this.nextTrack(true);
      } else {
        this.isPlaying = false;
        // 整本书播放完成，可以选择清除播放位置记录
        // this.clearPlaybackPosition();
      }
    },

    onPlay() {
      this.isPlaying = true;
    },

    onPause() {
      this.isPlaying = false;
    },

    // 字幕方法
    parseSRT(content) {
      const cues = [];
      // 兼容 SRT 的 HH:MM:SS,mmm 与 WebVTT 省略小时的 MM:SS.mmm
      const timeRe = /(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})\s*-->\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})/;
      const blocks = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split(/\n\n+/);
      for (const block of blocks) {
        const lines = block.split('\n');
        const timeLineIdx = lines.findIndex(l => timeRe.test(l));
        if (timeLineIdx === -1) continue;
        const m = lines[timeLineIdx].match(timeRe);
        const start = (+(m[1] || 0)) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4].padEnd(3, '0')) / 1000;
        const end = (+(m[5] || 0)) * 3600 + (+m[6]) * 60 + (+m[7]) + (+m[8].padEnd(3, '0')) / 1000;
        const text = lines.slice(timeLineIdx + 1).join('\n').trim();
        if (text && end > start) {
          cues.push({ start, end, text });
        }
      }
      // 防御畸形文件：保证二分查找前提（按开始时间有序）
      cues.sort((a, b) => a.start - b.start);
      return cues;
    },

    async loadSubtitle(url) {
      this.subtitleCues = [];
      this.currentCueIndex = -1;
      if (!url || !process.client) return;

      if (this.subtitleCache[url]) {
        this.subtitleCues = this.subtitleCache[url];
        return;
      }

      try {
        const resp = await fetch(url, { credentials: 'include' });
        if (!resp.ok) return;
        const content = await resp.text();
        const cues = this.parseSRT(content);
        this.subtitleCache[url] = cues;
        // 防止快速切轨时旧请求覆盖新字幕
        const currentAudio = this.currentAudio;
        if (currentAudio && currentAudio.subtitle === url) {
          this.subtitleCues = cues;
        }
      } catch (error) {
        console.error('Failed to load subtitle:', error);
      }
    },

    syncSubtitle() {
      if (!this.subtitleCues.length) return;
      // 使用播放器绝对时间：普通分章文件与 currentTime 一致；
      // m4b 内嵌章节共享整条音轨的外挂字幕时，字幕时间轴为绝对时间
      const player = this.$refs.audioPlayer;
      const t = player ? player.currentTime : this.currentTime;
      let lo = 0;
      let hi = this.subtitleCues.length - 1;
      let idx = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const c = this.subtitleCues[mid];
        if (t < c.start) {
          hi = mid - 1;
        } else if (t >= c.end) {
          lo = mid + 1;
        } else {
          idx = mid;
          break;
        }
      }
      if (idx !== this.currentCueIndex) {
        this.currentCueIndex = idx;
      }
    },

    seekToCue(cue) {
      if (!cue || !this.$refs.audioPlayer) return;
      // 字幕时间为音轨绝对时间，直接设置即可（分章文件两者等价）
      this.$refs.audioPlayer.currentTime = cue.start;
    },

    toggleSubtitle() {
      this.showSubtitle = !this.showSubtitle;
      if (process.client) {
        try {
          localStorage.setItem('audio_subtitle_enabled', this.showSubtitle ? '1' : '0');
        } catch (error) {
          console.error('Error saving subtitle preference:', error);
        }
      }
    },

    restoreSubtitlePreference() {
      if (!process.client) return;
      try {
        const saved = localStorage.getItem('audio_subtitle_enabled');
        if (saved !== null) {
          this.showSubtitle = saved === '1';
        }
      } catch (error) {
        console.error('Error restoring subtitle preference:', error);
      }
    },

    // 工具方法
    getDisplayName(filename) {
      // 移除前缀（4个数字加下划线）
      return filename.replace(/^\d{4}_/, '');
    },

    formatTime(seconds) {
      if (!seconds || isNaN(seconds)) return '00:00';
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    },

    formatFileSize(bytes) {
      if (!bytes) return '';
      const mb = bytes / (1024 * 1024);
      return `${mb.toFixed(1)}MB`;
    },

    // 播放位置管理方法
    getStorageKey() {
      // 生成存储键：audio_progress_用户ID_书籍ID
      const userId = this.$store.state.user?.id || 'guest';
      return `audio_progress_${userId}_${this.bookId}`;
    },

    savePlaybackPosition() {
      if (!process.client || !this.bookId) return;

      try {
        const progressData = {
          trackIndex: this.currentTrackIndex,
          currentTime: this.currentTime,
          timestamp: Date.now(),
          bookTitle: this.book.title || '',
          totalTracks: this.audioFiles.length
        };

        localStorage.setItem(this.getStorageKey(), JSON.stringify(progressData));
        console.log('Saved playback position:', progressData);
      } catch (error) {
        console.error('Error saving playback position:', error);
      }
    },

    restorePlaybackPosition() {
      if (!process.client || !this.bookId || this.audioFiles.length === 0) return;

      try {
        const saved = localStorage.getItem(this.getStorageKey());
        if (!saved) return;

        const progressData = JSON.parse(saved);

        // 验证数据的有效性
        if (
          progressData.trackIndex >= 0 &&
          progressData.trackIndex < this.audioFiles.length &&
          progressData.currentTime >= 0
        ) {
          console.log('Restoring playback position:', progressData);

          // 恢复播放位置
          this.currentTrackIndex = progressData.trackIndex;

          // 加载对应的音频文件并传入保存的时间
          this.loadTrack(this.currentTrackIndex, progressData.currentTime);

          // 显示恢复提示信息
          if (this.$refs.audioPlayer && progressData.currentTime > 10) {
            this.showRestoreMessage(progressData);
          }
        }
      } catch (error) {
        console.error('Error restoring playback position:', error);
      }
    },

    showRestoreMessage(progressData) {
      // 可以在这里添加一个提示消息，告知用户已恢复播放位置
      const minutes = Math.floor(progressData.currentTime / 60);
      const seconds = Math.floor(progressData.currentTime % 60);
      const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;

      console.log(`已恢复到第${progressData.trackIndex + 1}章 ${timeStr} 的播放位置`);

      // 这里可以添加 toast 通知或其他 UI 提示
      // 例如：this.$toast.info(`已恢复到第${progressData.trackIndex + 1}章 ${timeStr} 的播放位置`);
    },

    startProgressSaving() {
      // 每5秒自动保存一次播放进度
      this.saveProgressInterval = setInterval(() => {
        if (this.isPlaying && this.currentTime > 0) {
          this.savePlaybackPosition();
        }
      }, 5000);
    },

    stopProgressSaving() {
      if (this.saveProgressInterval) {
        clearInterval(this.saveProgressInterval);
        this.saveProgressInterval = null;
      }
    },

    clearPlaybackPosition() {
      // 清除播放位置记录（可用于"从头开始"功能）
      if (!process.client || !this.bookId) return;

      try {
        localStorage.removeItem(this.getStorageKey());
        console.log('Cleared playback position for book:', this.bookId);
      } catch (error) {
        console.error('Error clearing playback position:', error);
      }
    },

    startFromBeginning() {
      // 从头开始播放
      this.clearPlaybackPosition();
      this.currentTrackIndex = 0;
      this.currentTime = 0;
      this.loadTrack(0);

      console.log('Started from beginning');
    },

    async downloadCollection() {
      if (!this.bookId || this.audioFiles.length === 0) {
        return;
      }

      this.downloadLoading = true;

      try {
        const response = await this.$backend(`/audios/${this.bookId}/collection`);

        if (response.err === 'ok') {
          // 成功获取下载链接，直接下载
          const link = document.createElement('a');
          link.href = response.download_url;
          link.style.display = 'none';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        } else {
          this.$alert('error', response.msg || this.$t('audio.downloadFailed'));
        }
      } catch (error) {
        console.error('Download collection error:', error);
        this.$alert('error', this.$t('audio.downloadFailed'));
      } finally {
        this.downloadLoading = false;
      }
    },

    async purchaseAudio() {
      if (!this.bookId) {
        return;
      }

      this.purchaseLoading = true;

      try {
        const response = await this.$backend(`/audio/${this.bookId}/purchase`, {
          method: 'POST',
          data: {
            price: 10.00
          }
        });

        if (response.err === 'ok') {
          this.isPaid = true;
          this.showPurchaseDialog = false;
          this.$alert('success', this.$t('audio.purchaseSuccess'));
        } else {
          this.$alert('error', response.msg || this.$t('audio.purchaseFailed'));
        }
      } catch (error) {
        console.error('Purchase audio error:', error);
        this.$alert('error', this.$t('audio.purchaseFailed'));
      } finally {
        this.purchaseLoading = false;
      }
    },

    gotoBookDetail() {
      this.$router.push("/book/" + this.bookId);
    },

    closePlayer() {
      // 停止播放并保存当前位置
      if (this.$refs.audioPlayer) {
        this.$refs.audioPlayer.pause();
      }
      this.savePlaybackPosition();

      // 退出播放界面
      this.$router.go(-1); // 返回上一页
    },

    openDeleteDialog() {
      this.showDeleteDialog = true;
    },

    async deleteAudio() {
      if (!this.bookId) {
        return;
      }

      this.deleteLoading = true;

      try {
        // 停止播放器
        if (this.$refs.audioPlayer) {
          this.$refs.audioPlayer.pause();
        }

        // 调用删除接口
        const response = await this.$backend(`/audio/${this.bookId}/delete`, {
          method: 'POST'
        });

        if (response.err === 'ok') {
          this.showDeleteDialog = false;
          this.$alert('success', this.$t('audio.deleteSuccess'));
          this.$router.go(-1);
        } else {
          this.$alert('error', response.msg || this.$t('audio.deleteFailed'));
        }
      } catch (error) {
        console.error('Delete audio error:', error);
        this.$alert('error', this.$t('audio.deleteFailed'));
      } finally {
        this.deleteLoading = false;
      }
    },

    async showPurchaseDialogWithVipInfo() {
      try {
        // 获取用户VIP信息
        const response = await this.$backend('/user/vip');
        if (response.err === 'ok') {
          // 使用临时变量存储当前查询的配额值
          this.vipquota = response.vipquota || 0;
          if (this.vipquota === 0) {
            this.$alert('error', this.$t('audio.vipQuotaInsufficient'));
          } else {
            this.showPurchaseDialog = true;
          }
        } else {
          // 如果获取VIP信息失败，直接显示购买对话框
          this.$alert('error', '无法获取账号信息，请稍后再试。');
        }
      } catch (error) {
        console.error('Error fetching VIP info:', error);
        // 如果网络错误，直接显示购买对话框
        this.$alert('error', '无法获取账号信息，请稍后再试。');
      }
    }
  }
};
</script>

<style scoped>
.audio-player-container {
  height: 100vh;
  background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
  color: #ffffff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.audio-upper-section {
  height: 60%;
  display: flex;
  padding: 20px;
  gap: 20px;
}

.cover-section {
  flex: 0 0 35%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cover-container {
  max-width: 300px;
  width: 100%;
  text-align: center;
}

.book-cover {
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  margin-bottom: 20px;
  cursor: pointer;
  transition: transform 0.3s ease, filter 0.3s ease;
}

.book-cover >>> .v-image__image {
  transition: transform 0.3s ease, filter 0.3s ease;
}

.book-cover:hover >>> .v-image__image {
  transform: scale(1.02);
  filter: brightness(1.1);
}

.book-title {
  font-size: 1.5rem;
  font-weight: bold;
  margin-bottom: 8px;
  color: #ffffff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.book-author {
  font-size: 1rem;
  color: #cccccc;
  margin: 0;
}

.playlist-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.playlist-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #404040;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 48px;
}

.playlist-header h3 {
  margin: 0;
  color: #ffffff;
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.playlist-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
  margin-left: auto;
}

.close-btn {
  background-color: #404040 !important;
  color: white !important;
  border-color: #666666 !important;
  white-space: nowrap;
  flex-shrink: 0;
}

.delete-btn {
  background: linear-gradient(135deg, #e53935 0%, #c62828 100%) !important;
  color: white !important;
  border: 1px solid #b71c1c !important;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.3s ease;
  margin-left: 8px;
}

.delete-btn:hover {
  background: linear-gradient(135deg, #c62828 0%, #b71c1c 100%) !important;
  box-shadow: 0 6px 8px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  transform: translateY(-1px);
}

.delete-btn:active {
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  transform: translateY(0);
}

.download-btn {
  background-color: #404040 !important;
  color: white !important;
  border-color: #666666 !important;
  white-space: nowrap;
  flex-shrink: 0;
  margin-right: 8px;
}

.download-btn:hover {
  background-color: #9C27B0 !important;
}

.download-btn:disabled {
  background-color: #2a2a2a !important;
  color: #666666 !important;
}

.chapter-info {
  background-color: transparent !important;
  color: white !important;
  border-color: #666666 !important;
  margin-right: 8px;
  white-space: nowrap;
  font-weight: 500;
}

.chapter-info .v-chip__content {
  color: white !important;
  font-size: 13px;
}

.playlist-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: #555555 #2c2c2c;
}

.playlist-container::-webkit-scrollbar {
  width: 6px;
}

.playlist-container::-webkit-scrollbar-track {
  background: #2c2c2c;
}

.playlist-container::-webkit-scrollbar-thumb {
  background: #555555;
  border-radius: 3px;
}

.playlist-item {
  display: flex;
  align-items: center;
  padding: 12px;
  cursor: pointer;
  border-radius: 8px;
  margin-bottom: 4px;
  transition: all 0.2s;
  min-width: 0;
}

.playlist-item:hover {
  background-color: #404040;
}

.playlist-item.active {
  background-color: #9C27B0;
}

.track-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: #555555;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  margin-right: 12px;
  flex-shrink: 0;
}

.playlist-item.active .track-number {
  background-color: rgba(255, 255, 255, 0.2);
}

.playlist-item.locked {
  opacity: 0.5;
  color: #aaa;
  cursor: not-allowed;
}

.playlist-item.locked:hover {
  background-color: transparent;
}

.vip-badge {
  margin-left: 8px;
}

.purchase-btn {
  margin-right: 8px;
}

.purchase-hint {
  margin-top: 8px;
}

.track-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.track-title {
  font-weight: 500;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-duration {
  font-size: 0.875rem;
  color: #cccccc;
}

.no-audio-message {
  text-align: center;
  padding: 40px 20px;
  color: #888888;
}

.audio-controls-section {
  height: 40%;
  background: #1a1a1a;
  border-top: 1px solid #404040;
  padding: 10px;
  display: flex;
  flex-direction: column;
}

.progress-section {
  margin-bottom: 20px;
}

.time-display {
  display: flex;
  justify-content: space-between;
  font-size: 0.875rem;
  color: #cccccc;
  margin-bottom: 8px;
}

.progress-slider {
  margin: 0;
}

/* 字幕显示区 */
.subtitle-section {
  min-height: 44px;
  max-height: 72px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px 16px;
}

.subtitle-text {
  font-size: 1rem;
  line-height: 1.5;
  color: #e0e0e0;
  background: rgba(0, 0, 0, 0.45);
  border-radius: 8px;
  padding: 6px 14px;
  text-align: center;
  white-space: pre-wrap;
  word-break: break-word;
  cursor: pointer;
  transition: background 0.2s ease;
  max-width: 100%;
}

.subtitle-text:hover {
  background: rgba(156, 39, 176, 0.35);
}

.controls-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}

.main-controls {
  display: flex;
  align-items: center;
  gap: 20px;
}

.control-btn {
  background-color: #404040 !important;
}

.nav-btn:not(:disabled) {
  background-color: #404040 !important;
  color: white !important;
}

.nav-btn:disabled {
  background-color: #2a2a2a !important;
  color: #666666 !important;
}

.play-btn {
  background-color: #9C27B0 !important;
  color: white !important;
}

.secondary-controls {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  justify-content: center;
}

.speed-btn,
.timer-btn,
.subtitle-btn {
  background-color: #404040 !important;
  color: white !important;
  position: relative;
}

.speed-text {
  position: absolute;
  bottom: -2px;
  right: -2px;
  font-size: 10px;
  background-color: #9C27B0;
  border-radius: 50%;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.volume-slider {
  margin: 0;
}

/* 中等屏幕适配 (平板横屏) */
@media (max-width: 1024px) and (min-width: 769px) {
  .audio-upper-section {
    padding: 15px;
    gap: 15px;
  }

  .cover-container {
    max-width: 250px;
  }

  .playlist-header h3 {
    font-size: 1.3rem;
  }
}

/* 移动端适配 */
@media (max-width: 768px) {
  .audio-upper-section {
    flex-direction: column;
    height: 50%;
    padding: 10px;
  }

  .subtitle-section {
    min-height: 36px;
    max-height: 56px;
    padding: 2px 8px;
  }

  .subtitle-text {
    font-size: 0.875rem;
    padding: 4px 10px;
  }

  .cover-section {
    display: none; /* 移动端隐藏封面 */
  }

  .playlist-section {
    flex: 1;
    min-height: 0;
  }

  .playlist-header {
    position: sticky;
    top: 0;
    background: #2c2c2c;
    z-index: 10;
    margin-bottom: 8px;
    padding: 8px 0;
  }

  .playlist-controls {
    flex-direction: row;
    gap: 8px;
    justify-content: flex-end; /* 保持右对齐 */
    flex-wrap: wrap; /* 允许换行 */
  }

  .chapter-info {
    order: 1;
  }

  .download-btn {
    order: 2;
    font-size: 12px;
    padding: 0 6px;
    min-width: auto;
  }

  .close-btn {
    order: 3;
  }

  .playlist-container {
    padding-top: 0;
  }

  .audio-controls-section {
    height: 50%;
    padding: 15px;
  }

  .secondary-controls {
    flex-direction: row;
    gap: 15px;
    justify-content: center;
  }

  .main-controls {
    gap: 15px;
  }

  .progress-section {
    margin-bottom: 15px;
  }
}

/* 竖屏专用样式 */
@media (max-width: 480px) and (orientation: portrait) {
  .audio-upper-section {
    height: 60%;
    padding: 8px;
  }

  .audio-controls-section {
    height: 40%;
    padding: 12px;
  }

  .playlist-header h3 {
    font-size: 1.1rem;
  }

  .playlist-controls {
    gap: 6px;
  }

  .chapter-info {
    font-size: 12px;
    height: 24px;
  }

  .download-btn {
    min-width: auto;
    padding: 0 6px;
    font-size: 11px;
  }

  .download-btn .v-icon {
    margin-right: 2px !important;
  }

  .close-btn {
    min-width: auto;
    padding: 0 8px;
  }

  .close-btn .v-icon {
    margin-right: 4px !important;
  }

  .track-title {
    font-size: 14px;
  }

  .track-duration {
    font-size: 12px;
  }
}

/* 全局样式覆盖 */
:global(body.audio-player-page) {
  background: #1a1a1a !important;
}

:global(.audio-player-page .v-application) {
  background: #1a1a1a !important;
}

:global(.audio-player-page .v-navigation-drawer),
:global(.audio-player-page .v-app-bar) {
  display: none !important;
}

:global(.audio-player-page .v-main) {
  padding: 0 !important;
}
</style>
