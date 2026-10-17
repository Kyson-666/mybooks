<template>
    <v-dialog :value="open" @input="$emit('update:open', $event)" persistent width="480">
        <v-card class="dialog-border">
            <v-toolbar flat dense dark color="#003153" class="dialog-toolbar">
                {{ $t('book.audioList') }}
                <span v-if="audios.status === audioStatus.PROCESSING && audios.progress && audios.progress.converted_chapters !== undefined"
                      class="ml-2 text-caption">
                    ({{ audios.progress.converted_chapters }}/{{ audios.progress.total_chapters }})
                </span>
                <v-spacer></v-spacer>
                <v-btn color="" text @click="$emit('update:open', false)">{{ $t('common.close') }}</v-btn>
            </v-toolbar>
            <div style="height: 16px;"></div>
            <v-card-text v-if="audios.status === audioStatus.PROCESSING">
                <p style="color: orange; font-weight: bold;">{{ $t('book.conversionInProgress') }}</p>
                <v-progress-linear
                    v-if="audios.progress && audios.progress.total_chapters > 0"
                    :value="(audios.progress.converted_chapters / audios.progress.total_chapters) * 100"
                    color="primary"
                    height="6"
                ></v-progress-linear>
            </v-card-text>
            <v-card-text v-if="audios.status === audioStatus.FAILED">
                <p style="color: red; font-weight: bold;">{{ $t('book.conversionFailed') }}</p>
                <p style="color: red; font-weight: bold;">
                    {{ audios.progress && audios.progress.error_message ? audios.progress.error_message : $t('book.defaultFailedReason') }}
                </p>
            </v-card-text>
            <v-card-text>
                <p>{{ $t('book.convertToAudioNote') }}</p>
                <div class="audio-scroll-container" style="max-height: 200px; overflow-y: auto; overflow-x: hidden; padding: 12px 12px 0 12px;">
                    <v-row v-for="(audio_item, idx) in audios.audios" :key="'audio-' + idx" class="mb-2">
                        <v-col class='py-0'>
                            <v-btn
                                icon
                                small
                                @click="playAudioFile(audio_item, idx)"
                                :loading="playing_audio_index === idx && audio_loading"
                                :color="playing_audio_index === idx ? 'primary' : 'default'"
                            >
                                <v-icon>{{ playing_audio_index === idx && !audio_paused ? 'mdi-pause' : 'mdi-play' }}</v-icon>
                            </v-btn>
                            <span class="ml-2">{{ audio_item.filename }}</span>
                        </v-col>
                    </v-row>
                </div>
            </v-card-text>
            <v-card-actions class="justify-center">
                <v-btn
                    v-if="audios.status === audioStatus.PROCESSING"
                    color="warning"
                    @click="$emit('clear-conversion')"
                >
                    {{ $t('book.cancelConversion') }}
                </v-btn>
                <v-btn
                    v-else-if="audios.status === audioStatus.CONVERTED"
                    color="error"
                    @click="$emit('clear-conversion')"
                >
                    {{ $t('common.clear') }}
                </v-btn>
                <v-btn
                    v-if="audios.status === audioStatus.CONVERTED"
                    color="primary"
                    @click="$emit('generate-audio')"
                >
                    {{ $t('common.restore') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script>
export default {
    name: "AudioListDialog",
    props: {
        open: { type: Boolean, default: false },
        audios: { type: Object, required: true },
        audioStatus: { type: Object, required: true },
    },
    data() {
        return {
            playing_audio_index: null,
            audio_loading: false,
            audio_paused: false,
            currentAudioFile: null,
        };
    },
    beforeDestroy() {
        this.stopAudioFilePlayback();
    },
    methods: {
        playAudioFile(audioItem, index) {
            if (this.playing_audio_index === index && this.currentAudioFile) {
                if (this.audio_paused) {
                    this.currentAudioFile.play();
                    this.audio_paused = false;
                } else {
                    this.currentAudioFile.pause();
                    this.audio_paused = true;
                }
                return;
            }
            this.stopAudioFilePlayback();
            this.$emit('stop-sample-audio');
            this.audio_loading = true;
            this.playing_audio_index = index;
            this.currentAudioFile = new Audio(audioItem.url);
            this.currentAudioFile.addEventListener('loadstart', () => { this.audio_loading = true; });
            this.currentAudioFile.addEventListener('canplay', () => { this.audio_loading = false; });
            this.currentAudioFile.addEventListener('ended', () => { this.stopAudioFilePlayback(); });
            this.currentAudioFile.addEventListener('error', () => {
                this.stopAudioFilePlayback();
                this.$alert("error", this.$t('message.audioLoadFailed'));
            });
            this.currentAudioFile.play().then(() => {
                this.audio_loading = false;
                this.audio_paused = false;
            }).catch(() => {
                this.stopAudioFilePlayback();
                this.$alert("error", this.$t('message.audioPlayFailed'));
            });
        },
        stopAudioFilePlayback() {
            if (this.currentAudioFile) {
                this.currentAudioFile.pause();
                this.currentAudioFile = null;
            }
            this.playing_audio_index = null;
            this.audio_loading = false;
            this.audio_paused = false;
        },
    },
};
</script>
