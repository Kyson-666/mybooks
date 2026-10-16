<template>
  <div id="txt-main">
    <v-navigation-drawer v-model="sidebar" app fixed width="240"
                         class="d-flex flex-column" style="height: 100%"
                         :clipped="$vuetify.breakpoint.lgAndUp">
      <v-subheader style="height: 48px">{{ name }}</v-subheader>
      <v-virtual-scroll
        style="height: calc(100% - 48px)"
        :items="content" bench="20"
        item-height="40">
        <template v-slot:default="{item,index}">
          <v-list-item dense :key="item.title" @click="getNovelContent(index)"
                       :color="selected===index?'primary':''">
            <v-list-item-content>
              <v-list-item-title>
                {{ item.title }}
              </v-list-item-title>
            </v-list-item-content>
          </v-list-item>
        </template>
      </v-virtual-scroll>
    </v-navigation-drawer>

    <v-app-bar class="px-0" color="blue" dense dark app fixed clipped-left extension-height="64">

      <v-toolbar-title class="ml-n5 mr-12 align-center">
        <v-app-bar-nav-icon @click.stop="sidebar = !sidebar">
          <v-icon>mdi-menu</v-icon>
        </v-app-bar-nav-icon>
        <span class="cursor-pointer" @click="$router.push('/')">
          {{ name }}
        </span>
      </v-toolbar-title>

    </v-app-bar>
    <div>
      <v-container>
        <v-card outlined v-if="!inited" width="300" style="margin: 0 auto">
          <v-card-title ref="tipTitle">{{ tip.title }}</v-card-title>
          <v-card-text ref="tip" class="text-center">
            <v-progress-circular v-if="!tip.content" color="primary" indeterminate size="28"/>
            <span v-else>{{ tip.content }}</span>
          </v-card-text>
        </v-card>
        <div v-else>
          <div class="text-center caption grey--text" style="margin-bottom: 10px" v-if="!tocReady">
            {{ tocHint }}
          </div>
          <div class="d-flex justify-center align-content-center" style="margin-bottom: 20px" v-if="loading">
            <v-progress-circular color="primary" indeterminate size="28" style="margin-right: 10px"/>
            {{ $t('reader.loading') }}
          </div>
          <div style="word-wrap: break-word" v-html="novelContent" v-show="!loading"/>
          <div class="d-flex justify-space-between" v-show="novelContent && !loading">
            <v-btn color="info" elevation="0" :disabled="!tocReady || selected<=0"
                   @click="getNovelContent(selected-1)">
              {{ $t('reader.previous') }}
            </v-btn>
            <v-btn outlined elevation="0" @click="sidebar=true" v-show="tocReady && !sidebar">
              {{ $t('reader.directory') }}
            </v-btn>
            <v-btn color="primary" elevation="0" :disabled="!tocReady || selected>=content.length-1"
                   @click="getNovelContent(selected+1)">
              {{ $t('reader.next') }}
            </v-btn>
          </div>
        </div>
        <app-footer v-if="$store.state.nav"></app-footer>
      </v-container>
    </div>
  </div>
</template>

<script>
import AppFooter from "~/components/AppFooter.vue"

// 打开时先直接渲染 txt 开头这么多字节，无需等待目录解析完成。
const PREVIEW_BYTES = 20000;

export default {
  name: "TxtReader",
  components: {AppFooter},
  data() {
    return {
      sidebar: null,
      bookid: null,
      content: [],
      inited: false,
      tocReady: false,
      pollTimer: null,
      hintText: '',
      name: null,
      novelContent: '',
      selected: -1,
      loading: true,
      tip: {
        title: '',
        content: ''
      }
    }
  },
  computed: {
    // 目录就绪前显示的非阻塞提示（队列/超时/错误优先，否则为“解析中”）
    tocHint() {
      return this.hintText || this.$t('reader.tocParsing');
    }
  },
  created() {
    this.bookid = this.$route.params.bid;
    this.$store.commit("navbar", false);
    this.tip.title = this.$t('reader.loading');
    this.tip.content = '';
    // 先把开头正文渲染出来，再请求目录：目录解析是整本扫描，与首屏并发会把
    // 服务端的预览响应一起拖慢（表现为长时间停在「加载中」）
    this.loadPreview().finally(() => {
      if (this.inited) this.loadToc();
    });
  },
  beforeDestroy() {
    this.stopPolling();
  },
  methods: {
    // 立即渲染开头，不被目录解析阻塞
    loadPreview() {
      this.loading = true;
      return this.$backend(`/read/txt/${this.bookid}?start=0&end=${PREVIEW_BYTES}`)
        .then(res => {
          if (res.err === "ok" && res.content) {
            this.novelContent = res.content;
            this.inited = true;
          } else if (!this.inited) {
            this.showError(res && res.msg);
          }
        }).catch(() => {
        if (!this.inited) this.showError();
      }).finally(() => {
        this.loading = false;
      });
    },
    loadToc() {
      this.$backend(`/book/txt/parser?id=${this.bookid}&test=0`)
        .then(rsp => {
          if (rsp.err !== "ok") {
            this.hintText = rsp.msg;
            if (!this.inited) this.showError(rsp.msg);
            return;
          }
          if (rsp.msg === "parsed") {
            this.applyToc(rsp.data);
            return;
          }
          this.name = rsp.data.name;
          const queLen = parseInt(rsp.data.que);
          if (queLen > 0) {
            this.hintText = this.$t('reader.queueMessage', { queLen });
          }
          this.startPolling(parseInt(rsp.data.wait));
        })
        .catch(() => {
          if (!this.inited) this.showError();
        });
    },
    // 首屏加载/解析失败时在卡片上给出可读错误，避免一直转圈
    showError(msg) {
      this.tip.title = this.$t('reader.error');
      this.tip.content = msg || this.$t('reader.contentError', { msg: '' });
    },
    applyToc(data) {
      this.content = data.content;
      this.name = data.name;
      this.inited = true;
      this.tocReady = true;
      this.hintText = '';
      if (this.selected !== 0) {
        this.getNovelContent(0);
      }
    },
    startPolling(wait) {
      this.stopPolling();
      // 1 秒一跳；小文件 wait 值很小，用 30s 兜底，避免还没轮询就超时
      const budget = Math.max(parseInt(wait) || 0, 30);
      let elapsed = 0;
      this.pollTimer = setInterval(() => {
        elapsed++;
        if (elapsed > budget) {
          this.hintText = this.$t('reader.timeoutMessage');
          this.stopPolling();
          return;
        }
        if (elapsed % 3 !== 0) return;
        this.$backend(`/book/txt/parser?id=${this.bookid}&test=1`)
          .then(res => {
            if (res.err === "ok" && res.msg === "parsed") {
              this.applyToc(res.data);
              this.stopPolling();
            }
          })
      }, 1000)
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    },
    getNovelContent(i) {
      if (this.selected === i) return;
      this.selected = i;
      const {title, start, end} = {...this.content[i]};
      this.loading = true;
      this.$backend(`/read/txt/${this.bookid}?start=${start}&end=${end}`)
        .then(res => {
          if (res.err !== "ok") {
            this.novelContent = this.$t('reader.contentError', { msg: res.msg });
            return;
          }
          this.novelContent = title + "<br>" + res.content;
          this.inited = true;
        }).finally(() => {
        this.loading = false;
        document.getElementsByTagName('html')[0].style.scrollBehavior = 'smooth';
        document.getElementsByTagName('html')[0].scrollTop = 0;
      })
    }
  }
}
</script>

<style scoped>

</style>
