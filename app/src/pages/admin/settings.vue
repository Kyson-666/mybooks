<template>
  <div class="settings-page-root">
    <div class="d-flex justify-end flex-wrap mb-2" style="gap: 8px">
      <v-btn
        class="settings-hint-btn"
        href="https://www.zhihu.com/ring/host/2091200432408376415"
        target="_blank"
        rel="noopener"
      >
        <v-icon left>mdi-forum-outline</v-icon>
        {{ $t('settings.community') }}
      </v-btn>
      <v-btn
        class="settings-hint-btn"
        href="https://www.mybooks.top/docs/manual/"
        target="_blank"
        rel="noopener"
      >
        <v-icon left>mdi-lightbulb-question-outline</v-icon>
        {{ $t('settings.hint') }}
      </v-btn>
    </div>

    <v-sheet elevation="2" class="settings-group-bar">
      <div class="settings-group-bar-row d-flex align-center">
        <div class="settings-seg" role="tablist">
          <button
            v-for="g in groups"
            :key="g.id"
            type="button"
            role="tab"
            class="settings-seg-btn"
            :class="{ 'is-active': activeGroup === g.id && !searchQuery }"
            :aria-selected="activeGroup === g.id && !searchQuery"
            @click="selectGroup(g.id)"
          >
            <v-icon x-small>{{ g.icon }}</v-icon>
            {{ $t(g.title) }}
            <span class="settings-seg-bar" :style="{ background: groupAccent(g.id) }"></span>
          </button>
        </div>
        <div class="settings-bar-right d-flex align-center">
          <v-chip v-if="dirtyCount > 0" color="orange" text-color="white" small class="settings-status-chip">
            {{ $t('settings.unsaved_changes', { n: dirtyCount }) }}
          </v-chip>
          <v-chip v-else color="green" text-color="white" small class="settings-status-chip">
            {{ $t('settings.all_saved') }}
          </v-chip>
          <v-btn
            v-if="!searchOpen"
            icon
            class="settings-search-btn"
            :aria-label="$t('settings.search_placeholder')"
            @click="openSearch"
          >
            <v-icon>mdi-magnify</v-icon>
          </v-btn>
          <v-expand-x-transition>
            <v-text-field
              v-show="searchOpen"
              ref="searchField"
              v-model="searchQ"
              class="settings-search settings-search-expanded"
              dense
              outlined
              rounded
              hide-details
              prepend-inner-icon="mdi-magnify"
              append-icon="mdi-close"
              :placeholder="$t('settings.search_placeholder')"
              :aria-label="$t('settings.search_placeholder')"
              @click:append="closeSearch"
              @keydown.esc="closeSearch"
              @blur="onSearchBlur"
            ></v-text-field>
          </v-expand-x-transition>
        </div>
      </div>
    </v-sheet>

    <v-card v-if="searchQuery" class="my-2 elevation-4">
      <v-card-title>{{ $t('settings.search_results', { n: results.length }) }}</v-card-title>
      <v-card-text style="padding: 0 16px 16px">
        <p v-if="results.length === 0" class="grey--text">{{ $t('settings.search_no_results') }}</p>
        <template v-else>
          <div
            v-for="r in results"
            :key="r.key"
            class="settings-result d-flex align-center py-2"
            role="button"
            tabindex="0"
            @click="jumpTo(r)"
            @keydown.enter="jumpTo(r)"
            @keydown.space.prevent="jumpTo(r)"
          >
            <v-icon small class="mr-3" :color="r.red ? 'red' : 'grey'">{{ r.icon }}</v-icon>
            <div class="flex-grow-1">
              <div>{{ r.label }}</div>
              <div class="text-caption grey--text">{{ r.path }}</div>
            </div>
            <v-icon small color="grey">mdi-chevron-right</v-icon>
          </div>
        </template>
      </v-card-text>
    </v-card>

    <template v-else>
      <div v-for="g in currentGroups" :key="g.id">
        <div class="d-flex align-center flex-wrap mt-4 mb-2">
          <span class="settings-group-title-bar" :style="{ background: groupAccent(g.id) }"></span>
          <v-icon large color="primary" class="mr-3">{{ g.icon }}</v-icon>
          <div class="flex-grow-1">
            <div class="text-h5 font-weight-medium">{{ $t(g.title) }}</div>
          </div>
        </div>

        <v-card
          v-for="s in g.sections"
          :key="g.id + '-' + s.id"
          :id="'sec-' + g.id + '-' + s.id"
          class="my-2 elevation-4"
        >
          <v-card-title>
            <v-icon small color="primary" class="mr-2">{{ s.icon }}</v-icon>
            {{ $t(s.title) }}
          </v-card-title>
          <v-card-text style="padding: 8px 20px 20px">
            <p v-if="s.desc">{{ $t(s.desc) }}</p>
            <template v-if="s.tips">
              <p v-for="t in s.tips" :key="t.text">
                {{ $t(t.text) }}
                <a v-if="t.link" target="_blank" :href="t.link">{{
                  $t("settings.link")
                }}</a>
              </p>
            </template>

            <div class="pl-6" v-if="s.fields && s.fields.length" :class="{ 'settings-fields-2col': s.fields.some((x) => x.half) }">
            <template v-for="f in s.fields">
              <div :key="'w-' + f.key" :id="'f-' + f.key" :class="f.half ? 'settings-field-half' : 'settings-field-full'">
              <v-checkbox
                small
                hide-details
                v-if="f.type === 'checkbox'"
                v-model="settings[f.key]"
                :key="f.key + '-checkbox'"
                :label="$t(f.label)"
              >
                <template v-if="f.icon" v-slot:prepend>
                  <v-icon :color="f.color">{{ f.icon }}</v-icon>
                </template>
              </v-checkbox>
              <div
                v-else-if="f.type === 'checkbox_list'"
                :key="f.key + '-checkbox_list'"
                class="mb-2"
              >
                <div class="d-flex align-center mt-2">
                  <v-icon class="mr-2" :color="f.color">{{ f.icon }}</v-icon>
                  <span class="text-body-1">{{ $t(f.label) }}</span>
                </div>
                <div v-if="f.tips" class="text-caption grey--text ml-8">{{ $t(f.tips) }}</div>
                <div class="pl-8">
                  <v-row dense>
                    <v-col
                      v-for="opt in f.items"
                      :key="f.key + '-' + opt.value"
                      cols="12"
                      sm="6"
                    >
                      <v-checkbox
                        v-model="settings[f.key]"
                        :value="opt.value"
                        :label="$t(opt.text)"
                        dense
                        hide-details
                        class="mt-0"
                      ></v-checkbox>
                    </v-col>
                  </v-row>
                </div>
              </div>
              <div
                v-else-if="f.type === 'subtitle'"
                :key="f.key + '-subtitle'"
                class="d-flex align-center mt-2 mb-1"
              >
                <v-icon small class="mr-2" :color="f.color">{{ f.icon }}</v-icon>
                <span class="text-body-1">{{ $t(f.label) }}</span>
              </div>
              <v-textarea
                outlined
                v-else-if="f.type === 'textarea'"
                v-model="settings[f.key]"
                :key="f.key + '-textarea'"
                :label="$t(f.label)"
              >
                <template v-if="f.icon" v-slot:prepend>
                  <v-icon :color="f.color">{{ f.icon }}</v-icon>
                </template>
              </v-textarea>
              <v-select
                small
                v-else-if="f.type === 'select'"
                v-model="settings[f.key]"
                :items="f.items"
                :key="f.key + '-select'"
                :label="$t(f.label)"
              >
                <template v-if="f.icon" v-slot:prepend>
                  <v-icon :color="f.color">{{ f.icon }}</v-icon>
                </template>
                <template v-slot:item="{ item, attrs, on }">
                  <v-list-item v-on="on" v-bind="attrs">
                    <v-list-item-icon v-if="item.icon">
                      <v-icon>{{ item.icon }}</v-icon>
                    </v-list-item-icon>
                    <v-list-item-content>
                      <v-list-item-title>{{ item.text }}</v-list-item-title>
                    </v-list-item-content>
                  </v-list-item>
                </template>
                <template v-slot:selection="{ item }">
                  <v-icon v-if="item.icon" left>{{ item.icon }}</v-icon>
                  {{ item.text }}
                </template>
              </v-select>
              <v-select
                small
                v-else-if="f.type === 'select_image'"
                v-model="settings[f.key]"
                :items="f.items"
                :key="f.key + '-select_image'"
                :label="$t(f.label)"
              >
                <template v-if="f.icon" v-slot:prepend>
                  <v-icon :color="f.color">{{ f.icon }}</v-icon>
                </template>
                <template #item="{ item }">
                  <v-img
                    :src="`${site_url}/logo/${item.image_file}.ico`"
                    max-width="32"
                    max-height="32"
                  />
                </template>
                <template #selection="{ item }">
                  <v-img
                    :src="`${site_url}/logo/${item.image_file}.ico`"
                    max-width="32"
                    max-height="32"
                  />
                </template>
              </v-select>
              <template v-else-if="f.type === 'meta_sources'">
                <v-select
                  :key="f.key + '-meta_sources'"
                  small
                  ref="metaSourceSelect"
                  v-model="settings['META_SELECTED_SOURCES']"
                  :items="metaSourceItems"
                  :label="$t(f.label)"
                  multiple
                  chips
                  small-chips
                >
                  <template v-slot:selection="{ item }">
                    <v-chip
                      small
                      @click.stop="
                        $refs.metaSourceSelect[0]
                          ? $refs.metaSourceSelect[0].activateMenu()
                          : $refs.metaSourceSelect.activateMenu()
                      "
                    >
                      {{ item.text }}
                    </v-chip>
                  </template>
                  <template v-slot:item="{ item, attrs, on }">
                    <v-list-item v-on="on" v-bind="attrs">
                      <v-list-item-action>
                        <v-checkbox
                          :input-value="attrs.inputValue"
                          color="primary"
                        ></v-checkbox>
                      </v-list-item-action>
                      <v-list-item-content>
                        <v-list-item-title>{{ item.text }}</v-list-item-title>
                      </v-list-item-content>
                    </v-list-item>
                  </template>
                  <template v-if="f.icon" v-slot:prepend>
                    <v-icon :color="f.color">{{ f.icon }}</v-icon>
                  </template>
                </v-select>
              </template>
              <book-nav-editor
                v-else-if="f.type === 'book_nav'"
                :key="f.key + '-book_nav'"
                v-model="bookNavList"
              ></book-nav-editor>
              <v-text-field
                v-else-if="f.type === 'number'"
                v-model.number="settings[f.key]"
                :key="f.key + '-number'"
                :label="$t(f.label)"
                type="number"
                min="0"
              >
                <template v-if="f.icon" v-slot:prepend>
                  <v-icon :color="f.color">{{ f.icon }}</v-icon>
                </template>
              </v-text-field>
              <v-text-field
                v-else
                v-model="settings[f.key]"
                :key="f.key + '-text'"
                :label="$t(f.label)"
                type="text"
              >
                <template v-if="f.icon" v-slot:prepend>
                  <v-icon :color="f.color">{{ f.icon }}</v-icon>
                </template>
              </v-text-field>
              </div>
            </template>
            </div>

            <template v-for="b in (s.actions || [])">
              <v-btn :key="b.label" @click="run(b.action)" color="primary"
                ><v-icon>{{ b.icon }}</v-icon
                >{{ $t(b.label) }}</v-btn
              >
            </template>

            <div class="pl-6" v-if="s.groups && s.groups.length">
            <template v-for="grp in s.groups">
              <v-checkbox
                :key="grp.key"
                small
                hide-details
                v-model="settings[grp.key]"
                :label="$t(grp.label)"
                :prepend-icon="grp.icon"
                @change="$delete(forceOpen, grp.key)"
              >
              </v-checkbox>
              <template v-if="settings[grp.key] || forceOpen[grp.key]">
                <div class="pl-6" :key="grp.key + '-fields'">
                <template v-for="f in grp.fields">
                  <div :key="'w-' + f.key" :id="'f-' + f.key">
                  <v-checkbox
                    small
                    hide-details
                    v-if="f.type === 'checkbox'"
                    :prepend-icon="f.icon"
                    v-model="settings[f.key]"
                    :key="f.key + '-checkbox'"
                    :label="$t(f.label)"
                  ></v-checkbox>
                  <v-textarea
                    outlined
                    v-else-if="f.type === 'textarea'"
                    :prepend-icon="f.icon"
                    v-model="settings[f.key]"
                    :key="f.key"
                    :label="$t(f.label)"
                  ></v-textarea>
                  <div
                    v-else-if="f.type === 'reading_range'"
                    :key="f.key + '-reading_range'"
                  >
                    <p class="mb-2">{{ defaultReadRangeSummary }}</p>
                    <v-btn
                      color="primary"
                      @click="openDefaultReadRangeDialog"
                    >
                      <v-icon left>mdi-book-cog-outline</v-icon>
                      {{ $t(f.label) }}
                    </v-btn>
                  </div>
                  <v-text-field
                    v-else
                    :prepend-icon="f.icon"
                    v-model="settings[f.key]"
                    :key="f.key + '-text'"
                    :label="$t(f.label)"
                    type="text"
                  ></v-text-field>
                  </div>
                </template>
                </div>
              </template>
            </template>
            </div>

            <template v-if="s.special === 'friends'">
              <div class="pl-6">
              <v-row
                v-for="(friend, idx) in settings.FRIENDS"
                :key="'friend-' + friend.href"
              >
                <v-col class="py-0" cols="3">
                  <v-text-field
                    flat
                    small
                    hide-details
                    single-line
                    v-model="friend.text"
                    :label="$t('settings.name')"
                    type="text"
                  ></v-text-field>
                </v-col>
                <v-col class="py-0" cols="9">
                  <v-text-field
                    flat
                    small
                    hide-details
                    single-line
                    v-model="friend.href"
                    :label="$t('settings.link')"
                    type="text"
                    append-outer-icon="mdi-delete"
                    @click:append-outer="settings.FRIENDS.splice(idx, 1)"
                  ></v-text-field>
                </v-col>
              </v-row>
              <v-row>
                <v-col align="center">
                  <v-btn
                    color="primary"
                    @click="settings.FRIENDS.push({ text: '', href: '' })"
                    ><v-icon>mdi-plus</v-icon>{{ $t("settings.add") }}</v-btn
                  >
                </v-col>
              </v-row>
              </div>
            </template>

            <template v-if="s.special === 'reader_dicts'">
              <reader-dict-editor
                v-model="settings.READER_MYDICTS"
                :mybooks-enabled.sync="settings.READER_DICT_MYBOOKS_ENABLED"
                :baike-enabled.sync="settings.READER_DICT_BAIKE_ENABLED"
              ></reader-dict-editor>
            </template>

            <template v-if="s.special === 'devices'">
              <div class="pl-6">
              <template v-for="(device, idx) in settings.DEVICES">
                <div :key="'device-' + idx" class="device-item mb-3">
                  <v-row>
                    <v-col class="py-1" cols="3">
                      <v-text-field
                        outlined
                        dense
                        hide-details="auto"
                        v-model="device.name"
                        :label="$t('settings.device_name')"
                        type="text"
                        maxlength="64"
                      ></v-text-field>
                    </v-col>
                    <v-col class="py-1" cols="2">
                      <v-select
                        outlined
                        dense
                        hide-details="auto"
                        v-model="device.type"
                        :items="deviceTypes"
                        :label="$t('settings.device_type')"
                      ></v-select>
                    </v-col>
                    <template v-if="device.type === 'kindle'">
                      <v-col class="py-1" cols="6">
                        <v-text-field
                          outlined
                          dense
                          hide-details="auto"
                          v-model="device.mailbox"
                          :label="$t('settings.device_mailbox')"
                          type="email"
                          placeholder="user@kindle.com"
                        ></v-text-field>
                      </v-col>
                    </template>
                    <template v-else-if="device.type === 'ftp'">
                      <v-col class="py-1" cols="3">
                        <v-text-field
                          outlined
                          dense
                          hide-details="auto"
                          v-model="device.ip"
                          :label="$t('settings.device_ip')"
                          type="text"
                          placeholder="192.168.1.100"
                        ></v-text-field>
                      </v-col>
                      <v-col class="py-1" cols="2">
                        <v-text-field
                          outlined
                          dense
                          hide-details="auto"
                          v-model.number="device.port"
                          :label="$t('settings.device_port')"
                          type="number"
                          placeholder="21"
                        ></v-text-field>
                      </v-col>
                    </template>
                    <template v-else>
                      <v-col class="py-1" cols="2">
                        <v-text-field
                          outlined
                          dense
                          hide-details="auto"
                          v-model="device.ip"
                          :label="$t('settings.device_ip')"
                          type="text"
                          placeholder="192.168.1.100"
                        ></v-text-field>
                      </v-col>
                      <v-col class="py-1" cols="2">
                        <v-text-field
                          outlined
                          dense
                          hide-details="auto"
                          v-model.number="device.port"
                          :label="$t('settings.device_port')"
                          type="number"
                          placeholder="8080"
                        ></v-text-field>
                      </v-col>
                      <v-col class="py-1" cols="2">
                        <v-select
                          outlined
                          dense
                          hide-details="auto"
                          v-model="device.schema"
                          :items="deviceSchemas"
                          :label="$t('settings.device_schema')"
                        ></v-select>
                      </v-col>
                    </template>
                    <v-col class="py-1" cols="auto" align-self="center">
                      <v-btn icon small @click="settings.DEVICES.splice(idx, 1)">
                        <v-icon>mdi-delete</v-icon>
                      </v-btn>
                    </v-col>
                  </v-row>
                  <v-row v-if="device.type === 'ftp'">
                    <v-col class="py-1" cols="3"></v-col>
                    <v-col class="py-1" cols="2">
                      <v-text-field
                        outlined
                        dense
                        hide-details="auto"
                        v-model="device.ftp_username"
                        :label="$t('settings.device_ftp_username')"
                        type="text"
                        autocomplete="off"
                        :placeholder="$t('book.ftpAnonymousHint')"
                      ></v-text-field>
                    </v-col>
                    <v-col class="py-1" cols="2">
                      <v-text-field
                        outlined
                        dense
                        hide-details="auto"
                        v-model="device.ftp_password"
                        :label="$t('settings.device_ftp_password')"
                        type="password"
                        autocomplete="new-password"
                      ></v-text-field>
                    </v-col>
                    <v-col class="py-1" cols="3">
                      <v-text-field
                        outlined
                        dense
                        hide-details="auto"
                        v-model="device.ftp_path"
                        :label="$t('settings.device_ftp_path')"
                        type="text"
                        placeholder="/books"
                      ></v-text-field>
                    </v-col>
                  </v-row>
                </div>
              </template>
              <v-row>
                <v-col align="center">
                  <v-btn
                    color="primary"
                    @click="
                      settings.DEVICES.push({
                        name: $t('settings.default_reader_name'),
                        type: 'duokan',
                        ip: '',
                        port: 12121,
                        schema: 'http',
                      })
                    "
                  >
                    <v-icon>mdi-plus</v-icon>{{ $t("settings.add") }}
                  </v-btn>
                </v-col>
              </v-row>
              </div>
            </template>

            <template v-if="s.special === 'bookbarn'">
              <p>{{ $t("settings.book_barn_description") }}</p>
              <div class="pl-6">
              <v-checkbox
                small
                hide-details
                v-model="settings['ENABLE_BOOKBARN']"
                :key="'ENABLE_BOOKBARN'"
                :label="$t('settings.bookbarn_enable')"
              ></v-checkbox>
              <v-text-field
                flat
                small
                v-model="settings['BOOKBARN_TOKEN']"
                :label="$t('settings.bookbarn_token')"
                type="text"
                :disabled="true"
              ></v-text-field>
              <v-btn
                color="primary"
                :disabled="!settings['ENABLE_BOOKBARN'] || appliedToken"
                style="margin-bottom: 24px"
                @click="applyBookbarnToken"
              >
                <v-icon>mdi-key</v-icon>{{ $t("settings.bookbarn_apply_token") }}
              </v-btn>
              </div>
            </template>

            <template v-if="s.special === 'ai_capabilities'">
              <p>{{ $t("settings.ai_capabilities_description") }}</p>
              <div class="pl-6">
              <v-checkbox
                small
                hide-details
                v-model="settings['AI_ENABLED']"
                :key="'AI_ENABLED'"
                :label="$t('settings.ai_enabled')"
              ></v-checkbox>
              <v-text-field
                :disabled="!settings['AI_ENABLED']"
                :prepend-icon="'mdi-key'"
                v-model="settings['AI_DEEPSEEK_API_KEY']"
                :label="$t('settings.ai_api_key')"
                :placeholder="$t('settings.ai_api_key_description')"
                type="text"
                :rules="apiKeyRules"
                :maxlength="128"
              ></v-text-field>
              <v-text-field
                :disabled="!settings['AI_ENABLED']"
                :prepend-icon="'mdi-link'"
                v-model="settings['AI_API_URL']"
                :label="$t('settings.ai_api_url')"
                :placeholder="$t('settings.ai_api_url_description')"
                type="text"
                :rules="[urlRule]"
                :maxlength="512"
              ></v-text-field>
              <v-text-field
                :disabled="!settings['AI_ENABLED']"
                :prepend-icon="'mdi-function'"
                v-model="settings['AI_MODEL']"
                :label="$t('settings.ai_model')"
                :placeholder="$t('settings.ai_model_description')"
                type="text"
                :rules="[modelNameRule]"
                :maxlength="128"
              ></v-text-field>
              <v-text-field
                :prepend-icon="'mdi-key'"
                v-model="settings['AI_MCP_TOKEN']"
                :label="$t('settings.ai_mcp_token')"
                type="text"
                :append-icon="'mdi-refresh'"
                @click:append="generateMCPToken"
                readonly
              ></v-text-field>
              <v-btn
                :disabled="!settings['AI_ENABLED'] || testingAI"
                color="green"
                class="white--text mt-3"
                @click="testAISettings"
              >
                <span v-if="testingAI" class="flex items-center gap-2">
                  <img :src="site_url + '/icons/loading.svg'" width="20" height="20" />
                  {{ $t('settings.testing') }}
                </span>
                <span v-else>{{ $t('settings.test_ai_settings') }}</span>
              </v-btn>
              <v-divider class="my-2"></v-divider>
              <v-checkbox
                small
                hide-details
                :disabled="!settings['AI_ENABLED']"
                v-model="settings['AI_ALLOW_SET_CATEGORY']"
                :key="'AI_ALLOW_SET_CATEGORY'"
                :label="$t('settings.ai_allow_set_category')"
                class="mb-3"
                prepend-icon="mdi-scatter-plot-outline"
              ></v-checkbox>
              </div>
            </template>

            <template v-if="s.special === 'socials'">
              <p>{{ $t("settings.socials_description") }}</p>
              <div class="pl-6">
              <v-combobox
                v-model="settings.SOCIALS"
                :items="sns_items"
                :label="$t('settings.select_socials')"
                hide-selected
                multiple
                small-chips
              >
                <template v-slot:selection="{ attrs, item, parent, selected }">
                  <v-chip
                    v-bind="attrs"
                    color="green lighten-3"
                    :input-value="selected"
                    label
                    small
                  >
                    <span class="pr-2"> {{ item.text }} </span>
                    <v-icon small @click="parent.selectItem(item)"
                      >mdi-close</v-icon
                    >
                  </v-chip>
                </template>
              </v-combobox>
              <v-row v-for="s2 in settings.SOCIALS" :key="'social-' + s2.value">
                <v-col class="py-0" cols="12" sm="2">
                  <v-subheader
                    class="px-0 pt-4"
                    :class="$vuetify.breakpoint.smAndUp ? 'float-right' : ''"
                  >
                    {{ s2.text }} (<a @click="showSNSConfig(s2)">{{
                      $t("settings.description")
                    }}</a
                    >)
                  </v-subheader>
                </v-col>
                <v-col class="py-0" cols="12" sm="3">
                  <v-text-field
                    small
                    hide-details
                    single-line
                    v-model="
                      settings['SOCIAL_AUTH_' + s2.value.toUpperCase() + '_KEY']
                    "
                    :label="Key"
                    placeholder="Key/AppID"
                    type="text"
                  ></v-text-field>
                </v-col>
                <v-col class="py-0" cols="12" sm="7">
                  <v-text-field
                    small
                    hide-details
                    single-line
                    v-model="
                      settings[
                        'SOCIAL_AUTH_' + s2.value.toUpperCase() + '_SECRET'
                      ]
                    "
                    :label="Secert"
                    placeholder="Secret"
                    type="text"
                  ></v-text-field>
                </v-col>
              </v-row>
              </div>
            </template>

            <template v-if="s.special === 'trash'">
              <div class="text-center">
                <p v-html="$t('settings.trash_description')"></p>
                <div style="font-size: 1.2em; margin-bottom: 8px">
                  {{ $t("settings.trash_calibre_size") }}
                  <span style="font-weight: bold; color: #1976d2">{{
                    trashSizeTexts.trash
                  }}</span>
                </div>
                <div style="font-size: 1.2em; margin-bottom: 16px">
                  {{ $t("settings.trash_upload_size") }}
                  <span style="font-weight: bold; color: #1976d2">{{
                    trashSizeTexts.upload
                  }}</span>
                </div>
                <v-btn
                  color="red"
                  dark
                  @click="trashConfirmDialog = true"
                  style="margin-bottom: 24px"
                  :disabled="
                    trashSizes.trash + trashSizes.upload <= 10 * 1048576
                  "
                >
                  <v-icon>mdi-delete</v-icon>{{ $t("settings.trash_clear_button") }}
                </v-btn>
                <p class="mt-2">
                  <nuxt-link to="/admin/trash">{{
                    $t("settings.trash_books_goto_management")
                  }}</nuxt-link>
                </p>
              </div>
            </template>

            <template v-if="s.special === 'perf'">
              <div class="pl-6">
                <v-checkbox
                  small
                  v-model="liteMode"
                  prepend-icon="mdi-speedometer"
                  :label="$t('settings.perf_mode_lite')"
                  :hint="$t('settings.perf_mode_hint')"
                  persistent-hint
                ></v-checkbox>
                <div v-if="liteMode" style="padding-left: 32px">
                  <v-checkbox
                    v-for="key in liteGroups"
                    :key="key"
                    small
                    dense
                    v-model="settings[key]"
                    :label="$t('settings.' + key.toLowerCase())"
                    :hint="$t('settings.' + key.toLowerCase() + '_hint')"
                    persistent-hint
                  ></v-checkbox>
                </div>
                <v-checkbox
                  small
                  v-model="thumbCache"
                  prepend-icon="mdi-image-multiple-outline"
                  :label="$t('settings.thumb_cache')"
                  :hint="$t('settings.thumb_cache_hint')"
                  persistent-hint
                ></v-checkbox>
                <div v-if="thumbCache" style="padding-left: 32px; padding-top: 14px">
                  <v-select
                    v-model="cacheMaxMb"
                    :items="cacheSizeItems"
                    :label="$t('settings.thumb_cache_size')"
                    dense
                    style="max-width: 240px"
                  ></v-select>
                </div>
              </div>
            </template>

            <template v-if="s.special === 'stamp'">
              <div class="pl-6">
              <v-checkbox
                small
                hide-details
                v-model="settings['ENABLE_STAMP_FEATURE']"
                :label="$t('settings.enable_stamp_feature')"
                prepend-icon="mdi-picture-in-picture-bottom-right-outline"
              ></v-checkbox>
              <div v-if="settings['ENABLE_STAMP_FEATURE']" style="margin-top: 16px; margin-left: 16px;">
                <v-row align="top">
                  <v-col cols="12" sm="6">
                    <p class="mb-2">{{ $t('settings.stamp_image_label') }}</p>
                    <div style="position: relative; width: 200px; height: 200px;">
                      <v-img
                        :src="stampPreviewUrl"
                        width="200"
                        height="200"
                        style="border: 1px solid #ddd;"
                        contain
                      >
                        <template v-slot:placeholder>
                          <v-row
                            class="fill-height ma-0"
                            align="center"
                            justify="center"
                          >
                            <v-icon size="80" color="grey lighten-2">mdi-image</v-icon>
                          </v-row>
                        </template>
                      </v-img>
                      <v-btn
                        absolute
                        bottom
                        right
                        fab
                        small
                        color="primary"
                        @click="openStampFileDialog"
                        style="margin: 8px;"
                      >
                        <v-icon>mdi-upload</v-icon>
                      </v-btn>
                      <input
                        ref="stampFileInput"
                        type="file"
                        accept=".png"
                        style="display: none"
                        @change="uploadStampImage"
                      />
                    </div>
                    <p class="text-caption mt-2">
                      {{ $t('settings.stamp_image_hint') }}
                    </p>
                  </v-col>
                </v-row>
              </div>
              </div>
            </template>

            <template v-if="s.special === 'ssl'">
              <div class="pl-6">
              <ssl-manager />
              </div>
            </template>
          </v-card-text>
        </v-card>
      </div>
    </template>

    <v-card class="my-2 elevation-4" v-if="thanksToNames.length > 0">
      <v-card-title @click="thanksToShow = !thanksToShow">
        <v-btn @click.once="thanksToShow = !thanksToShow" icon>
          <v-icon>{{
            thanksToShow ? "mdi-chevron-down" : "mdi-chevron-up"
          }}</v-icon>
        </v-btn>
        <v-icon color="red" small class="thanks-heart-icon mr-1">mdi-heart</v-icon>
        {{ $t("settings.thanksTo") }}
        <v-icon color="red" small class="thanks-heart-icon ml-1">mdi-heart</v-icon>
      </v-card-title>
      <v-expand-transition>
        <v-card-text v-show="thanksToShow" style="padding: 0">
          <div style="padding: 0 16px 16px">
            <div class="thanks-to-section">
              <p class="thanks-to-desc">{{ $t("settings.thanksToDesc") }}</p>
              <div class="thanks-to-names">
                <span v-for="(name, idx) in thanksToNames" :key="idx" class="thanks-to-chip">{{ name }}</span>
              </div>
            </div>
          </div>
        </v-card-text>
      </v-expand-transition>
    </v-card>

    <AppDialog
      v-model="trashConfirmDialog"
      type="confirm"
      :title="$t('settings.trash_clear_confirm_title')"
      color="deep-orange"
      confirm-dark
      max-width="400"
      :confirm-text="$t('settings.trash_clear_confirm_button')"
      @confirm="clearTrash"
    >
      {{ $t("settings.trash_clear_confirm_message") }}
    </AppDialog>

    <AppDialog
      v-model="restartConfirmDialog"
      type="confirm"
      :title="$t('settings.restart_confirm_title')"
      color="orange"
      confirm-dark
      max-width="400"
      :confirm-text="$t('settings.restart_confirm_button')"
      @confirm="restartServer"
    >
      {{ $t("settings.restart_confirm_message") }}
    </AppDialog>

    <reading-range-dialog
      ref="defaultReadRangeDialog"
      :title="$t('settings.default_read_range_dialog_title')"
      :saving="savingDefaultReadRange"
      @save="saveDefaultReadRange"
    ></reading-range-dialog>

    <div class="settings-savebar">
      <v-icon small :color="dirtyCount > 0 ? 'orange' : 'green'" class="mr-2">
        {{ dirtyCount > 0 ? "mdi-pencil-box-outline" : "mdi-check-circle" }}
      </v-icon>
      <span
        class="text-caption"
        :class="dirtyCount > 0 ? 'orange--text font-weight-bold' : 'grey--text'"
      >
        {{
          dirtyCount > 0
            ? $t("settings.savebar_unsaved", { n: dirtyCount })
            : $t("settings.all_saved")
        }}
      </span>
      <span class="text-caption grey--text ml-4 hidden-sm-and-down">{{ $t("settings.save_hints") }}</span>
      <v-spacer></v-spacer>
      <v-btn color="orange" dark @click="restartConfirmDialog = true">
        <v-icon left>mdi-restart</v-icon>{{ $t("settings.restart_server") }}
      </v-btn>
      <v-btn
        color="primary"
        class="ml-3"
        :disabled="dirtyCount === 0"
        @click="saveSettings"
      >
        <v-icon left>mdi-content-save</v-icon>{{ $t("settings.save") }}
      </v-btn>
    </div>
  </div>
</template>

<script>
import SSLManager from "~/components/SSLManager.vue";
import ReadingRangeDialog from "~/components/ReadingRangeDialog.vue";
import BookNavEditor, { createCategory } from "~/components/BookNavEditor.vue";
import ReaderDictEditor from "~/components/ReaderDictEditor.vue";
import { languageOptions } from "~/utils/languageCodes";
import { isHexColor, DEFAULT_ACCENT } from "~/utils/appearance";

const LITE_GROUPS = [
  "LITE_GROUP_LISTING",
  "LITE_GROUP_RECOMMEND",
  "LITE_GROUP_FILES",
  "LITE_GROUP_BACKGROUND",
  "LITE_GROUP_RESOURCES",
];

// 特殊块（动态列表/子组件）不在 groups.fields 里，搜索索引需在此手动注册
const SPECIAL_BLOCKS = [
  { key: "FRIENDS", label: "settings.friend_links", icon: "mdi-link-variant", gid: "site", sid: "site-friends" },
  { key: "READER_MYDICTS", label: "settings.sec_reader_dict", icon: "mdi-book-alphabet", gid: "reading", sid: "reader-dict", al: ["翻译"] },
  { key: "READER_DICT_MYBOOKS_ENABLED", label: "settings.reader_dict_mybooks", icon: "mdi-book-alphabet", gid: "reading", sid: "reader-dict" },
  { key: "READER_DICT_BAIKE_ENABLED", label: "settings.reader_dict_baike", icon: "mdi-book-alphabet", gid: "reading", sid: "reader-dict" },
  { key: "ENABLE_STAMP_FEATURE", label: "settings.enable_stamp_feature", icon: "mdi-picture-in-picture-bottom-right-outline", gid: "reading", sid: "reader-physical" },
  { key: "SOCIALS", label: "settings.select_socials", icon: "mdi-at", gid: "users", sid: "users-social", al: ["qq", "微信", "微博", "github", "oauth"] },
  { key: "DEVICES", label: "settings.device_mgt", icon: "mdi-tablet-cellphone", gid: "push", sid: "push-devices", al: ["kindle", "文石", "掌阅", "汉王", "当当", "koreader", "duokan", "ireader", "boox", "ftp"] },
  { key: "ENABLE_BOOKBARN", label: "settings.bookbarn_enable", icon: "mdi-key", gid: "services", sid: "svc-bookbarn" },
  { key: "BOOKBARN_TOKEN", label: "settings.bookbarn_token", icon: "mdi-key", gid: "services", sid: "svc-bookbarn" },
  { key: "AI_ENABLED", label: "settings.ai_enabled", icon: "mdi-scatter-plot-outline", gid: "services", sid: "svc-ai" },
  { key: "AI_DEEPSEEK_API_KEY", label: "settings.ai_api_key", icon: "mdi-key", gid: "services", sid: "svc-ai" },
  { key: "AI_API_URL", label: "settings.ai_api_url", icon: "mdi-link", gid: "services", sid: "svc-ai" },
  { key: "AI_MODEL", label: "settings.ai_model", icon: "mdi-function", gid: "services", sid: "svc-ai" },
  { key: "AI_MCP_TOKEN", label: "settings.ai_mcp_token", icon: "mdi-key", gid: "services", sid: "svc-ai" },
  { key: "AI_ALLOW_SET_CATEGORY", label: "settings.ai_allow_set_category", icon: "mdi-scatter-plot-outline", gid: "services", sid: "svc-ai" },
  { key: "SSL", label: "settings.ssl_certificate_management", icon: "mdi-lock", gid: "protocols", sid: "proto-net", al: ["证书", "https"] },
  { key: "PERFORMANCE_MODE", label: "settings.perf_mode_lite", icon: "mdi-speedometer", gid: "ops", sid: "ops-perf", al: ["性能", "速度"] },
  { key: "LITE_GROUP_LISTING", label: "settings.lite_group_listing", icon: "mdi-speedometer", gid: "ops", sid: "ops-perf" },
  { key: "LITE_GROUP_RECOMMEND", label: "settings.lite_group_recommend", icon: "mdi-speedometer", gid: "ops", sid: "ops-perf" },
  { key: "LITE_GROUP_FILES", label: "settings.lite_group_files", icon: "mdi-speedometer", gid: "ops", sid: "ops-perf" },
  { key: "LITE_GROUP_BACKGROUND", label: "settings.lite_group_background", icon: "mdi-speedometer", gid: "ops", sid: "ops-perf" },
  { key: "LITE_GROUP_RESOURCES", label: "settings.lite_group_resources", icon: "mdi-speedometer", gid: "ops", sid: "ops-perf" },
  { key: "THUMB_CACHE", label: "settings.thumb_cache", icon: "mdi-image-multiple-outline", gid: "ops", sid: "ops-perf" },
  { key: "CACHE_MAX_MB", label: "settings.thumb_cache_size", icon: "mdi-image-multiple-outline", gid: "ops", sid: "ops-perf" },
  { key: "TRASH", label: "settings.trash_clear_button", icon: "mdi-delete", gid: "ops", sid: "ops-trash", al: ["回收站", "磁盘", "清理"] },
];

// 激活分组下色条 + 组标题竖条：默认跟随站点主色 accent（外观菜单里的「主色」），
// 换主色即时跟随
// （uiverse 分段 pill 的形态借鉴，样式为本仓 clean-room 实现）

// 用户口语搜索词（中文为主）→ 设置项 key
const SEARCH_ALIASES = {
  // 站点标识
  站名: ["site_title"], 名称: ["site_title", "DEVICES"], 标题: ["site_title", "push_title"],
  图标: ["site_icon"], favicon: ["site_icon"], logo: ["site_icon"],
  公告: ["HEADER"], 通知: ["HEADER", "SEND_MAIL_FOR_NEW_BOOKS"],
  脚注: ["FOOTER"], 页脚: ["FOOTER"],
  水印: ["FOOTER_WATERMARK"],
  语言: ["site_language", "DEFAULT_LANGUAGE"], 中文: ["site_language"], english: ["site_language"], 繁体: ["site_language"], 切换: ["site_language"],
  主页: ["INDEX_PAGE_TYPE", "MAIN_PAGE_RANDOM_COUNT", "MAIN_PAGE_RECENT_COUNT"], 默认页: ["INDEX_PAGE_TYPE"],
  项目链接: ["HIDE_PROJECT_LINKS"], 隐藏链接: ["HIDE_PROJECT_LINKS"],
  // 首页与列表
  随机: ["MAIN_PAGE_RANDOM_COUNT"], 推荐: ["RECOMMEND_ENABLE", "RECOMMEND_USE_CROWD", "ENABLE_BOOK_RECOMMEND_TO_OTHERS", "MAIN_PAGE_RANDOM_COUNT"], 智能: ["RECOMMEND_ENABLE"],
  协同: ["RECOMMEND_USE_CROWD"],
  分页: ["DEFAULT_PAGE_SIZE"], 每页: ["DEFAULT_PAGE_SIZE"],
  侧边栏: ["SIDEBAR_ITEMS"], 侧栏: ["SIDEBAR_ITEMS"], 菜单: ["SIDEBAR_ITEMS"],
  统计: ["ENABLE_HOMEPAGE_READING_STATS", "ALLOW_USER_DISABLE_STATISTIC"], banner: ["ENABLE_HOMEPAGE_READING_STATS"],
  在读: ["ENABLE_HOMEPAGE_READING_BOOKS"],
  书单: ["ENABLE_HOMEPAGE_BOOKLISTS", "BOOK_NAV"],
  // 分类设置
  分类: ["BOOK_NAV", "IMPORT_CATEGORY_WITH_FOLDER", "ENABLE_FOLDER_BROWSE", "AI_ALLOW_SET_CATEGORY"], 导航: ["BOOK_NAV"], 标签: ["BOOK_NAV"],
  // 阅读器与同步
  阅读器: ["EPUB_VIEWER", "DEVICES"], epub: ["EPUB_VIEWER"], epubjs: ["EPUB_VIEWER"], myreader: ["EPUB_VIEWER", "ENABLE_DATA_SYNC"],
  同步: ["ENABLE_DATA_SYNC", "ENABLE_WEBDAV_SERVICE", "WEBDAV_SYNC_FOLDER"], 进度: ["ENABLE_DATA_SYNC"],
  封面: ["USE_DYNAMIC_COVER", "ENABLE_STAMP_FEATURE", "THUMB_CACHE"],
  作者: ["ENABLE_AUTHOR_INFO"], 简介: ["ENABLE_AUTHOR_INFO"], 头像: ["ENABLE_AUTHOR_INFO"],
  隐私: ["ALLOW_USER_DISABLE_STATISTIC"], 采集: ["ALLOW_USER_DISABLE_STATISTIC"],
  笔记: ["ENABLE_SHARED_NOTES"], 划线: ["ENABLE_SHARED_NOTES"], 标注: ["ENABLE_SHARED_NOTES"],
  // 词典
  词典: ["READER_MYDICTS", "READER_DICT_MYBOOKS_ENABLED", "READER_DICT_BAIKE_ENABLED"],
  字典: ["READER_MYDICTS", "READER_DICT_MYBOOKS_ENABLED", "READER_DICT_BAIKE_ENABLED"],
  翻译: ["READER_MYDICTS", "READER_DICT_MYBOOKS_ENABLED", "READER_DICT_BAIKE_ENABLED"],
  生词: ["READER_MYDICTS"],
  百科: ["READER_DICT_BAIKE_ENABLED"], 百度百科: ["READER_DICT_BAIKE_ENABLED"],
  // 书评与互动
  评论: ["ENABLE_BOOK_REVIEW", "REVIEW_REQUIRES_APPROVAL", "ENABLE_BOOK_RECOMMEND_TO_OTHERS"], 评分: ["ENABLE_BOOK_REVIEW"], 书评: ["ENABLE_BOOK_REVIEW"], 打分: ["ENABLE_BOOK_REVIEW"],
  审核: ["REVIEW_REQUIRES_APPROVAL", "ENABLE_AUTO_NEW_USER_APPROVAL"],
  // 实体书与图章
  实体书: ["ENABLE_PHYSICAL_BOOKS", "ENABLE_BOOKS_TYPE_CONVERT_DIRECT"], 纸书: ["ENABLE_PHYSICAL_BOOKS"], 纸质书: ["ENABLE_PHYSICAL_BOOKS"],
  类型转换: ["ENABLE_BOOKS_TYPE_CONVERT_DIRECT"],
  文件夹: ["ENABLE_FOLDER_BROWSE"], 层级: ["ENABLE_FOLDER_BROWSE"],
  图章: ["ENABLE_STAMP_FEATURE"], 盖章: ["ENABLE_STAMP_FEATURE"], 印章: ["ENABLE_STAMP_FEATURE"],
  // 访客权限
  访客: ["ALLOW_GUEST_READ", "ALLOW_GUEST_DOWNLOAD", "ALLOW_GUEST_UPLOAD", "ALLOW_GUEST_PUSH"],
  游客: ["ALLOW_GUEST_READ", "ALLOW_GUEST_DOWNLOAD", "ALLOW_GUEST_UPLOAD", "ALLOW_GUEST_PUSH"],
  匿名: ["ALLOW_GUEST_READ", "ALLOW_GUEST_DOWNLOAD"], 免登录: ["ALLOW_GUEST_READ", "ALLOW_GUEST_DOWNLOAD", "ALLOW_GUEST_UPLOAD", "ALLOW_GUEST_PUSH"],
  // 注册与邀请
  邀请: ["INVITE_MODE", "INVITE_CODE"], 私人: ["INVITE_MODE"], 访问码: ["INVITE_MODE", "INVITE_CODE"], 注册码: ["INVITE_CODE", "INVITE_MODE"], 邀请码: ["INVITE_CODE", "INVITE_MODE"], 封闭: ["INVITE_MODE"],
  提示语: ["INVITE_MESSAGE"], 欢迎语: ["INVITE_MESSAGE"],
  注册: ["ALLOW_REGISTER", "SIGNUP_MAIL_TITLE", "ENABLE_AUTO_NEW_USER_APPROVAL"], 开放注册: ["ALLOW_REGISTER"],
  激活: ["SIGNUP_MAIL_TITLE", "SIGNUP_MAIL_CONTENT"],
  重置: ["RESET_MAIL_TITLE", "RESET_MAIL_CONTENT"], 找回: ["RESET_MAIL_TITLE", "RESET_MAIL_CONTENT"],
  密码: ["smtp_password", "cookie_secret", "INVITE_CODE", "AI_DEEPSEEK_API_KEY", "BOOKBARN_TOKEN", "RESET_MAIL_TITLE"],
  审批: ["ENABLE_AUTO_NEW_USER_APPROVAL"], 自动审批: ["ENABLE_AUTO_NEW_USER_APPROVAL"],
  // 默认权限与配额
  新用户: ["ALLOW_NEW_USER_MANAGE_BOOK", "ALLOW_NEW_USER_PUSH_BOOK", "ENABLE_AUTO_NEW_USER_APPROVAL", "DEFAULT_READ_RANGE"],
  权限: ["ALLOW_NEW_USER_MANAGE_BOOK", "ALLOW_NEW_USER_PUSH_BOOK", "ALLOW_READ_RANGE_SETTING"],
  白名单: ["ALLOW_READ_RANGE_SETTING", "DEFAULT_READ_RANGE"], 黑名单: ["ALLOW_READ_RANGE_SETTING", "DEFAULT_READ_RANGE"],
  可见: ["ALLOW_READ_RANGE_SETTING", "DEFAULT_READ_RANGE"], 屏蔽: ["ALLOW_READ_RANGE_SETTING", "DEFAULT_READ_RANGE"],
  范围: ["ALLOW_READ_RANGE_SETTING", "DEFAULT_READ_RANGE"],
  配额: ["ENABLE_DOWNLOAD_QUOTA", "GLOBAL_DOWNLOAD_QUOTA"], 下载: ["ENABLE_DOWNLOAD_QUOTA", "GLOBAL_DOWNLOAD_QUOTA", "ALLOW_GUEST_DOWNLOAD"], 每日: ["ENABLE_DOWNLOAD_QUOTA", "GLOBAL_DOWNLOAD_QUOTA"],
  // 社交登录
  登录: ["SOCIALS", "ALLOW_REGISTER", "INVITE_MODE"], 第三方: ["SOCIALS"], 社交: ["SOCIALS"], oauth: ["SOCIALS"], qq: ["SOCIALS"], 微信: ["SOCIALS"], 微博: ["SOCIALS"], github: ["SOCIALS"],
  // 上传
  扫描: ["scan_upload_path", "PDF_TILE_WITH_FILE_NAME"], 批量: ["scan_upload_path", "BATCH_ADD_IN_FORCE"],
  上传: ["MAX_UPLOAD_SIZE", "CHUNK_UPLOAD_SIZE", "scan_upload_path", "ALLOW_GUEST_UPLOAD", "KEEP_UPLOAD_SOURCE_FILE"],
  大小: ["MAX_UPLOAD_SIZE", "CACHE_MAX_MB"], 文件大小: ["MAX_UPLOAD_SIZE"],
  分片: ["CHUNK_UPLOAD_SIZE"], 大文件: ["CHUNK_UPLOAD_SIZE"],
  元数据: ["auto_fill_meta", "META_SELECTED_SOURCES", "DEFAULT_LANGUAGE"],
  源文件: ["KEEP_UPLOAD_SOURCE_FILE", "REMOVE_IMPORTED_FILE"], 保留: ["KEEP_UPLOAD_SOURCE_FILE"],
  // 导入规则
  pdf: ["PDF_TILE_WITH_FILE_NAME"], 文件名: ["PDF_TILE_WITH_FILE_NAME", "BOOK_NAMES_FORMAT"], 书名: ["PDF_TILE_WITH_FILE_NAME"],
  txt: ["ENABLE_TXT_TO_TXTZ_PLUGIN"], txtz: ["ENABLE_TXT_TO_TXTZ_PLUGIN"], 转换: ["ENABLE_TXT_TO_TXTZ_PLUGIN", "convert_timeout"],
  服务端: ["ENABLE_SERVER_FILE_IMPORT"],
  isbn: ["BATCH_ADD_IN_FORCE"], 强制: ["BATCH_ADD_IN_FORCE"], 无效: ["BATCH_ADD_IN_FORCE"],
  重复: ["UPLOAD_IGNORE_TITLE_CHECKING"], 同书: ["UPLOAD_IGNORE_TITLE_CHECKING"], 查重: ["UPLOAD_IGNORE_TITLE_CHECKING"],
  // 自动导入
  监控: ["IMPORT_BY_INOTIFY", "UPDATE_CATEGORY_WITH_FOLDER_RENAME"], 自动导入: ["IMPORT_BY_INOTIFY"], inotify: ["IMPORT_BY_INOTIFY"], 监视: ["IMPORT_BY_INOTIFY"],
  重命名: ["UPDATE_CATEGORY_WITH_FOLDER_RENAME"],
  // 存储布局
  拼音: ["BOOK_NAMES_FORMAT"], utf8: ["BOOK_NAMES_FORMAT"], 存储: ["BOOK_NAMES_FORMAT", "TRASH"],
  // 邮件服务
  smtp: ["smtp_server", "smtp_username", "smtp_password", "smtp_encryption"], 服务器: ["smtp_server"], 账号: ["smtp_username"],
  授权码: ["smtp_password"], 加密: ["smtp_encryption"], ssl: ["smtp_encryption", "SSL"], tls: ["smtp_encryption"], 端口: ["smtp_server", "smtp_encryption"],
  邮件: ["smtp_server", "smtp_username", "smtp_password", "smtp_encryption", "push_title", "push_content", "SEND_MAIL_FOR_NEW_BOOKS", "SIGNUP_MAIL_TITLE", "SIGNUP_MAIL_CONTENT", "RESET_MAIL_TITLE", "RESET_MAIL_CONTENT"],
  邮箱: ["smtp_server", "smtp_username", "smtp_password", "smtp_encryption", "push_title", "SEND_MAIL_FOR_NEW_BOOKS"],
  推送: ["DEVICES", "push_title", "push_content", "SEND_MAIL_FOR_NEW_BOOKS", "ALLOW_GUEST_PUSH", "ALLOW_NEW_USER_PUSH_BOOK", "smtp_server"],
  kindle: ["DEVICES", "push_title", "smtp_server"], 正文: ["push_content"],
  提醒: ["SEND_MAIL_FOR_NEW_BOOKS"], 新书: ["MAIN_PAGE_RECENT_COUNT", "SEND_MAIL_FOR_NEW_BOOKS"],
  // 推送设备
  设备: ["DEVICES"], 文石: ["DEVICES"], 掌阅: ["DEVICES"], 汉王: ["DEVICES"], 当当: ["DEVICES"], koreader: ["DEVICES"], duokan: ["DEVICES"], ireader: ["DEVICES"], boox: ["DEVICES"], purelibro: ["DEVICES"], ftp: ["DEVICES"],
  // 信息源
  信息: ["auto_fill_meta"], 刮削: ["auto_fill_meta", "META_SELECTED_SOURCES"],
  豆瓣: ["auto_fill_meta", "META_SELECTED_SOURCES", "douban_baseurl", "douban_apikey", "douban_max_count"], 书源: ["META_SELECTED_SOURCES", "auto_fill_meta"], 来源: ["META_SELECTED_SOURCES"],
  镜像: ["douban_baseurl"], api: ["AI_API_URL", "AI_DEEPSEEK_API_KEY", "douban_apikey", "douban_baseurl"],
  密钥: ["douban_apikey", "AI_DEEPSEEK_API_KEY", "cookie_secret", "AI_MCP_TOKEN", "BOOKBARN_TOKEN"],
  数量: ["douban_max_count", "MAIN_PAGE_RANDOM_COUNT", "MAIN_PAGE_RECENT_COUNT"],
  // 书栈
  书栈: ["ENABLE_BOOKBARN", "BOOKBARN_TOKEN"], barn: ["ENABLE_BOOKBARN"], token: ["BOOKBARN_TOKEN", "AI_MCP_TOKEN"], 令牌: ["BOOKBARN_TOKEN", "AI_MCP_TOKEN"],
  // AI 助手
  ai: ["AI_ENABLED", "AI_DEEPSEEK_API_KEY", "AI_API_URL", "AI_MODEL", "AI_MCP_TOKEN", "AI_ALLOW_SET_CATEGORY"],
  人工智能: ["AI_ENABLED"], 助手: ["AI_ENABLED"], deepseek: ["AI_ENABLED", "AI_DEEPSEEK_API_KEY", "AI_MODEL"],
  模型: ["AI_MODEL"], 接口: ["AI_API_URL"], url: ["AI_API_URL", "douban_baseurl"],
  mcp: ["AI_MCP_TOKEN"], 自动分类: ["AI_ALLOW_SET_CATEGORY"],
  // 服务与协议
  webdav: ["ENABLE_WEBDAV_SERVICE", "WEBDAV_SYNC_FOLDER"], 挂载: ["ENABLE_WEBDAV_SERVICE"], 可写: ["WEBDAV_SYNC_FOLDER"],
  opds: ["ENABLE_OPDS_SERVICE", "ENABLE_OPDS_AUTH"], 认证: ["ENABLE_OPDS_AUTH"],
  订阅: ["ENABLE_PODCAST_SERVICE", "ENABLE_OPDS_SERVICE"], 播客: ["ENABLE_PODCAST_SERVICE"], podcast: ["ENABLE_PODCAST_SERVICE"], 听书: ["ENABLE_PODCAST_SERVICE", "ALLOW_GUEST_READ"], 有声: ["ENABLE_AUDIO_CONVERSION_LOG", "ENABLE_AUDIO_SUBTITLE", "ENABLE_PODCAST_SERVICE"],
  cdn: ["static_host"], 域名: ["static_host"], 加速: ["static_host", "PERFORMANCE_MODE"], 静态: ["static_host"],
  cookie: ["cookie_secret"], 安全: ["cookie_secret", "INVITE_MODE", "ENABLE_OPDS_AUTH", "SSL", "AI_MCP_TOKEN"],
  证书: ["SSL", "static_host"], https: ["SSL", "static_host"],
  // 性能与缓存
  极速: ["PERFORMANCE_MODE"], 性能: ["PERFORMANCE_MODE", "THUMB_CACHE"], 低配: ["PERFORMANCE_MODE"], 卡: ["PERFORMANCE_MODE", "THUMB_CACHE"], 慢: ["PERFORMANCE_MODE", "THUMB_CACHE"], 速度: ["PERFORMANCE_MODE"],
  缓存: ["THUMB_CACHE", "CACHE_MAX_MB"], 缩略图: ["THUMB_CACHE"], 容量: ["CACHE_MAX_MB"], mb: ["CACHE_MAX_MB"],
  内存: ["LITE_GROUP_RESOURCES"], cpu: ["LITE_GROUP_RESOURCES", "PERFORMANCE_MODE"], 资源: ["LITE_GROUP_RESOURCES"],
  精简: ["LITE_GROUP_RECOMMEND", "LITE_GROUP_FILES", "LITE_GROUP_BACKGROUND"], 后台: ["LITE_GROUP_BACKGROUND"],
  // 日志与调试
  日志: ["LOG_LEVEL_DEBUG", "ENABLE_AUDIO_CONVERSION_LOG"], 调试: ["LOG_LEVEL_DEBUG"], debug: ["LOG_LEVEL_DEBUG"], 排错: ["LOG_LEVEL_DEBUG"],
  字幕: ["ENABLE_AUDIO_SUBTITLE"], srt: ["ENABLE_AUDIO_SUBTITLE"],
  重启: ["autoreload"], 生效: ["autoreload"], 超时: ["convert_timeout"], 时间: ["convert_timeout"],
  // 更新与工具箱
  更新: ["AUTO_CHECKING_NEW_VERSION", "ENABLE_TOOLBOX_STORE"], 版本: ["AUTO_CHECKING_NEW_VERSION"], 升级: ["AUTO_CHECKING_NEW_VERSION"], 检查: ["AUTO_CHECKING_NEW_VERSION"],
  工具箱: ["ENABLE_TOOLBOX_DEV_MODE", "ENABLE_TOOLBOX_STORE"], 开发者: ["ENABLE_TOOLBOX_DEV_MODE"], 商店: ["ENABLE_TOOLBOX_STORE"], 插件: ["ENABLE_TOOLBOX_STORE", "ENABLE_TXT_TO_TXTZ_PLUGIN"],
  // 维护与清理
  回收站: ["TRASH"], 清理: ["TRASH", "REMOVE_IMPORTED_FILE"], 磁盘: ["TRASH"], 空间: ["TRASH", "CACHE_MAX_MB"], 删除: ["TRASH", "REMOVE_IMPORTED_FILE"],
};

export default {
  components: {
    "ssl-manager": SSLManager,
    "reading-range-dialog": ReadingRangeDialog,
    "book-nav-editor": BookNavEditor,
    "reader-dict-editor": ReaderDictEditor,
  },
  created() {
    // 为body添加settings-page类名，应用背景图样式
    if (process.client) {
      document.body.classList.add("settings-page");
    }

    // 初始化设备类型选项
    this.deviceTypes = [
      { text: this.$t("settings.device_type_duokan"), value: "duokan" },
      { text: this.$t("settings.device_type_ireader"), value: "ireader" },
      { text: this.$t("settings.device_type_hanwang"), value: "hanwang" },
      { text: this.$t("settings.device_type_boox"), value: "boox" },
      { text: this.$t("settings.device_type_koreader"), value: "koreader" },
      { text: this.$t("settings.device_type_dangdang"), value: "dangdang" },
      { text: "Kindle", value: "kindle" },
      { text: "PureLibro", value: "purelibro" },
      { text: this.$t("settings.device_type_ftp"), value: "ftp" },
    ];

    // al = 搜索别名，供搜索匹配用
    this.groups = [
      {
        id: "site",
        icon: "mdi-web",
        title: "settings.group_site",
        sections: [
          {
            id: "site-id",
            icon: "mdi-home",
            title: "settings.sec_site_id",
            fields: [
              { icon: "mdi-home", key: "site_title", label: "settings.site_title" },
              {
                icon: "mdi-information",
                key: "site_icon",
                label: "settings.site_icon",
                type: "select_image",
                items: Array.from({ length: 9 }, (_, i) => ({
                  image_file: "favicon_" + i.toString(),
                  value: "favicon_" + i.toString(),
                })),
              },
              { icon: "mdi-copyright", key: "HEADER", label: "settings.site_header", type: "textarea" },
              { icon: "mdi-copyright", key: "FOOTER", label: "settings.site_footer", type: "textarea" },
              { icon: "mdi-closed-caption-outline", key: "FOOTER_WATERMARK", label: "settings.footer_watermark" },
              {
                icon: "mdi-web",
                key: "site_language",
                label: "settings.language_switch",
                type: "select",
                al: ["中文", "english", "繁體"],
                items: [
                  { text: this.$t('language.zh'), value: "zh" },
                  { text: this.$t('language.zh_TW'), value: "zh-TW" },
                  { text: this.$t('language.en'), value: "en" },
                ],
              },
              {
                icon: "mdi-home",
                key: "INDEX_PAGE_TYPE",
                label: "settings.index_page_type",
                type: "select",
                items: [
                  {
                    text: this.$t("settings.index_page_type_index"),
                    value: "index",
                  },
                  { text: this.$t("settings.index_page_type_all"), value: "all" },
                  {
                    text: this.$t("settings.index_page_type_categories"),
                    value: "categories",
                  },
                ],
              },
              {
                icon: "mdi-star-off-outline",
                key: "HIDE_PROJECT_LINKS",
                label: "settings.hide_project_link_in_footer",
                type: "checkbox",
              },
            ],
          },
          {
            id: "site-home",
            icon: "mdi-view-dashboard-outline",
            title: "settings.sec_site_home",
            fields: [
              {
                icon: "mdi-shuffle",
                key: "MAIN_PAGE_RANDOM_COUNT",
                label: "settings.main_page_random_count",
                type: "select",
                items: [0, 12, 24, 48, 96, 192, 768].map((v) => ({
                  text: String(v),
                  value: v,
                })),
              },
              {
                icon: "mdi-book-multiple",
                key: "MAIN_PAGE_RECENT_COUNT",
                label: "settings.main_page_recent_count",
                type: "select",
                items: [12, 24, 48, 96, 192].map((v) => ({
                  text: String(v),
                  value: v,
                })),
              },
              { icon: "mdi-auto-fix", key: "RECOMMEND_ENABLE", label: "settings.recommend_enable", type: "checkbox" },
              { icon: "mdi-account-group-outline", key: "RECOMMEND_USE_CROWD", label: "settings.recommend_use_crowd", type: "checkbox" },
              {
                icon: "mdi-book-multiple",
                key: "DEFAULT_PAGE_SIZE",
                label: "settings.default_page_size",
                type: "select",
                items: [60, 100, 200, 500, 1000].map((v) => ({
                  text: String(v),
                  value: v,
                })),
              },
              {
                icon: "mdi-page-layout-sidebar-left",
                key: "SIDEBAR_ITEMS",
                label: "settings.sidebar_items",
                type: "checkbox_list",
                tips: "settings.sidebar_items_tips",
                items: [
                  { value: "audiobooks", text: "appHeader.audioBooks" },
                  { value: "printbooks", text: "appHeader.physicalBooks" },
                  { value: "publishers", text: "appHeader.publishers" },
                  { value: "folders", text: "appHeader.folders" },
                  { value: "categories", text: "nav.categories" },
                  { value: "tags", text: "appHeader.tags" },
                  { value: "series", text: "appHeader.series" },
                  { value: "languages", text: "appHeader.languages" },
                  { value: "rating", text: "appHeader.rating" },
                  { value: "memo", text: "appHeader.memo" },
                ],
              },
              { icon: "mdi-eye-outline", key: "homepage-display-heading", label: "settings.homepage_display", type: "subtitle" },
              { icon: "mdi-chart-line", key: "ENABLE_HOMEPAGE_READING_STATS", label: "settings.enable_homepage_reading_stats", type: "checkbox", half: true },
              { icon: "mdi-book-open-page-variant-outline", key: "ENABLE_HOMEPAGE_READING_BOOKS", label: "settings.enable_homepage_reading_books", type: "checkbox", half: true },
              { icon: "mdi-format-list-bulleted-square", key: "ENABLE_HOMEPAGE_BOOKLISTS", label: "settings.enable_homepage_booklists", type: "checkbox", half: true },
              { icon: "mdi-thumb-up-outline", key: "ENABLE_BOOK_RECOMMEND_TO_OTHERS", label: "settings.enable_book_recommend_to_others", type: "checkbox", half: true },
            ],
          },
          {
            id: "site-cats",
            icon: "mdi-tag-outline",
            title: "settings.book_tags",
            desc: "settings.book_tags_description",
            fields: [
              { icon: "mdi-tag-outline", key: "BOOK_NAV", type: "book_nav", label: "settings.book_nav", al: ["书单", "分类", "导航"] },
            ],
          },
          {
            id: "site-friends",
            icon: "mdi-link-variant",
            title: "settings.friend_links",
            special: "friends",
          },
        ],
      },
      {
        id: "reading",
        icon: "mdi-book-open-page-variant",
        title: "settings.group_reading",
        sections: [
          {
            id: "reader-core",
            icon: "mdi-book-open",
            title: "settings.sec_reader_core",
            fields: [
              {
                icon: "mdi-book-open",
                key: "EPUB_VIEWER",
                label: "settings.epub_viewer",
                type: "select",
                items: [
                  { text: this.$t("settings.epubjs"), value: "epubjs.html", icon: "mdi-alpha-e-circle-outline" },
                  { text: this.$t("settings.myreader"), value: "MyReader", icon: "mdi-water-outline" }
                ],
              },
              { icon: "mdi-sync", key: "ENABLE_DATA_SYNC", label: "settings.enable_data_sync", type: "checkbox" },
              { icon: "mdi-image-sync-outline", key: "USE_DYNAMIC_COVER", label: "settings.use_dynamic_cover", type: "checkbox" },
              { icon: "mdi-face-man-outline", key: "ENABLE_AUTHOR_INFO", label: "settings.enable_author_info", type: "checkbox" },
              { icon: "mdi-chart-line", key: "ALLOW_USER_DISABLE_STATISTIC", label: "settings.allow_user_disable_statistic", type: "checkbox" },
              { icon: "mdi-note-multiple-outline", key: "ENABLE_SHARED_NOTES", label: "settings.enable_shared_notes", type: "checkbox" },
            ],
          },
          {
            id: "reader-dict",
            icon: "mdi-book-alphabet",
            title: "settings.sec_reader_dict",
            special: "reader_dicts",
          },
          {
            id: "reader-review",
            icon: "mdi-forum-outline",
            title: "settings.sec_reader_review",
            fields: [
              { icon: "mdi-star-outline", key: "ENABLE_BOOK_REVIEW", label: "settings.enable_book_review", type: "checkbox" },
              { icon: "mdi-shield-check-outline", key: "REVIEW_REQUIRES_APPROVAL", label: "settings.review_requires_approval", type: "checkbox" },
            ],
          },
          {
            id: "reader-physical",
            icon: "mdi-bookshelf",
            title: "settings.sec_reader_physical",
            groups: [
              {
                icon: "mdi-bookshelf",
                key: "ENABLE_PHYSICAL_BOOKS",
                label: "settings.enable_physical_books",
                type: "checkbox",
                fields: [
                  {
                    icon: "mdi-swap-horizontal",
                    key: "ENABLE_BOOKS_TYPE_CONVERT_DIRECT",
                    label: "settings.enable_book_type_convert_directly",
                    type: "checkbox",
                  }
                ]
              },
              {
                icon: "mdi-folder-multiple-outline",
                key: "ENABLE_FOLDER_BROWSE",
                label: "settings.enable_folder_browse",
                type: "checkbox",
              },
            ],
            special: "stamp",
          },
        ],
      },
      {
        id: "users",
        icon: "mdi-account-group-outline",
        title: "settings.group_users",
        sections: [
          {
            id: "users-guest",
            icon: "mdi-account",
            title: "settings.sec_users_guest",
            fields: [
              { icon: "mdi-read", key: "ALLOW_GUEST_READ", label: "settings.allow_guest_read", type: "checkbox" },
              { icon: "mdi-download", key: "ALLOW_GUEST_DOWNLOAD", label: "settings.allow_guest_download", type: "checkbox" },
              { icon: "mdi-upload", key: "ALLOW_GUEST_UPLOAD", label: "settings.allow_guest_upload", type: "checkbox" },
              { icon: "mdi-send", key: "ALLOW_GUEST_PUSH", label: "settings.allow_guest_push", type: "checkbox" },
            ],
          },
          {
            id: "users-reg",
            icon: "mdi-at",
            title: "settings.sec_users_reg",
            fields: [
              { icon: "mdi-subtitles-outline", key: "reset-mail-heading", label: "settings.sec_reset_mail", type: "subtitle" },
              {
                icon: "mdi-format-title",
                key: "RESET_MAIL_TITLE",
                label: "settings.reset_mail_title",
              },
              {
                icon: "mdi-subtitles-outline",
                key: "RESET_MAIL_CONTENT",
                label: "settings.reset_mail_content",
                type: "textarea",
              },
            ],
            groups: [
              {
                icon: "mdi-security",
                key: "INVITE_MODE",
                label: "settings.private_library_mode",
                al: ["访问码", "私人"],
                fields: [
                  {
                    icon: "mdi-lock",
                    key: "INVITE_CODE",
                    label: "settings.access_code",
                  },
                  {
                    icon: "mdi-account",
                    key: "INVITE_MESSAGE",
                    type: "textarea",
                    label: "settings.invite_message",
                  },
                ],
              },
              {
                icon: "mdi-at",
                key: "ALLOW_REGISTER",
                label: "settings.allow_guest_register",
                al: ["注册"],
                fields: [
                  {
                    icon: "mdi-format-title",
                    key: "SIGNUP_MAIL_TITLE",
                    label: "settings.signup_mail_title",
                  },
                  {
                    icon: "mdi-subtitles-outline",
                    key: "SIGNUP_MAIL_CONTENT",
                    label: "settings.signup_mail_content",
                    type: "textarea",
                  },
                  {
                    icon: "mdi-account-check-outline",
                    key: "ENABLE_AUTO_NEW_USER_APPROVAL",
                    label: "settings.enable_auto_new_user_approval",
                    type: "checkbox",
                  }
                ],
              },
            ],
          },
          {
            id: "users-default",
            icon: "mdi-download-lock-outline",
            title: "settings.sec_users_default",
            fields: [
              { icon: "mdi-book-multiple", key: "ALLOW_NEW_USER_MANAGE_BOOK", label: "settings.allow_new_user_manage_book", type: "checkbox" },
              { icon: "mdi-tablet-cellphone", key: "ALLOW_NEW_USER_PUSH_BOOK", label: "settings.allow_new_user_push_book", type: "checkbox" },
            ],
            groups: [
              {
                icon: "mdi-book-lock-outline",
                key: "ALLOW_READ_RANGE_SETTING",
                label: "settings.allow_read_range_setting",
                al: ["白名单", "黑名单"],
                fields: [
                  {
                    key: "DEFAULT_READ_RANGE",
                    type: "reading_range",
                    label: "settings.default_read_range",
                  },
                ],
              },
              {
                key: "ENABLE_DOWNLOAD_QUOTA",
                icon: "mdi-download-lock-outline",
                label: "settings.enable_download_quota",
                al: ["配额", "下载"],
                fields: [
                  {
                    icon: "mdi-counter",
                    key: "GLOBAL_DOWNLOAD_QUOTA",
                    label: "settings.global_download_quota",
                    type: "number",
                  }
                ],
              },
            ],
          },
          {
            id: "users-social",
            icon: "mdi-at",
            title: "settings.social_network_login",
            desc: "settings.socials_description",
            special: "socials",
          },
        ],
      },
      {
        id: "import",
        icon: "mdi-import",
        title: "settings.group_import",
        sections: [
          {
            id: "imp-upload",
            icon: "mdi-upload",
            title: "settings.sec_imp_upload",
            fields: [
              { icon: "mdi-import", key: "scan_upload_path", label: "settings.scan_upload_path" },
              {
                icon: "mdi-information",
                color: "red",
                key: "MAX_UPLOAD_SIZE",
                label: "settings.max_upload_size",
                al: ["上传"],
              },
              {
                icon: "mdi-information",
                key: "CHUNK_UPLOAD_SIZE",
                label: "settings.chunk_upload_size",
              },
              {
                icon: "mdi-translate",
                key: "DEFAULT_LANGUAGE",
                label: "settings.default_language",
                type: "select",
                items: languageOptions.map((lang) => ({
                  text: lang.name,
                  value: lang.code,
                })),
              },
              {
                icon: "mdi-file-lock-outline",
                key: "KEEP_UPLOAD_SOURCE_FILE",
                label: "settings.keep_upload_source_file",
                type: "checkbox",
              },
              {
                icon: "mdi-delete-circle-outline",
                key: "REMOVE_IMPORTED_FILE",
                label: "settings.remove_imported_file",
                type: "checkbox",
              },
            ],
          },
          {
            id: "imp-rules",
            icon: "mdi-import",
            title: "settings.sec_imp_rules",
            fields: [
              {
                icon: "mdi-file-pdf-box",
                key: "PDF_TILE_WITH_FILE_NAME",
                label: "settings.pdf_tile_with_file_name",
                type: "checkbox",
              },
              {
                icon: "mdi-format-text",
                color: "red",
                key: "ENABLE_TXT_TO_TXTZ_PLUGIN",
                label: "settings.enable_txt_to_txtz_plugin",
                type: "checkbox",
              },
              {
                icon: "mdi-server",
                key: "ENABLE_SERVER_FILE_IMPORT",
                label: "settings.enable_server_file_import",
                type: "checkbox",
              },
              {
                icon: "mdi-checkbox-marked-circle-plus-outline",
                key: "BATCH_ADD_IN_FORCE",
                label: "settings.batch_add_in_force",
                type: "checkbox",
              },
              {
                icon: "mdi-shape-plus",
                key: "IMPORT_CATEGORY_WITH_FOLDER",
                label: "settings.category_with_folder",
                type: "checkbox",
              },
              {
                icon: "mdi-pause-octagon",
                key: "auto_fill_pause_on_throttle",
                label: "settings.auto_fill_pause_on_throttle",
                type: "checkbox",
              },
              {
                icon: "mdi-file-document-outline",
                key: "UPLOAD_IGNORE_TITLE_CHECKING",
                label: "settings.upload_ignore_title_checking",
                type: "checkbox",
              },
            ],
          },
          {
            id: "imp-auto",
            icon: "mdi-crosshairs-gps",
            title: "settings.sec_imp_auto",
            groups: [
              {
                icon: "mdi-crosshairs-gps",
                key: "IMPORT_BY_INOTIFY",
                label: "settings.auto_importing",
                al: ["监控"],
                fields: [
                  {
                    icon: "mdi-swap-horizontal",
                    key: "UPDATE_CATEGORY_WITH_FOLDER_RENAME",
                    label: "settings.update_category_with_folder_rename",
                    type: "checkbox",
                  },
                ],
              },
            ],
          },
          {
            id: "imp-store",
            icon: "mdi-folder-multiple-outline",
            title: "settings.sec_imp_store",
            fields: [
              {
                icon: "mdi-information",
                color: "red",
                key: "BOOK_NAMES_FORMAT",
                label: "settings.book_names_format",
                type: "select",
                al: ["拼音", "utf8", "pinyin"],
                items: [
                  { text: this.$t("settings.pinyin_directory"), value: "en" },
                  { text: this.$t("settings.utf8_directory"), value: "utf8" },
                ],
              },
            ],
          },
        ],
      },
      {
        id: "push",
        icon: "mdi-email-send",
        title: "settings.group_push",
        sections: [
          {
            id: "push-smtp",
            icon: "mdi-email",
            title: "settings.email_service",
            desc: "settings.email_service_description",
            fields: [
              { icon: "mdi-email", key: "smtp_server", label: "settings.smtp_server" },
              {
                icon: "mdi-account",
                key: "smtp_username",
                label: "settings.smtp_username",
              },
              {
                icon: "mdi-lock",
                key: "smtp_password",
                label: "settings.smtp_password",
              },
              {
                icon: "mdi-information",
                key: "smtp_encryption",
                label: "settings.smtp_encryption",
                type: "select",
                items: [
                  { text: "SSL", value: "SSL" },
                  { text: "TLS", value: "TLS" },
                ],
              },
            ],
            actions: [
              { icon: "mdi-email", label: "settings.test_email", action: "testEmail" },
            ],
          },
          {
            id: "push-tpl",
            icon: "mdi-email-send",
            title: "settings.sec_push_tpl",
            fields: [
              { icon: "mdi-information", key: "push_title", label: "settings.push_title" },
              { icon: "mdi-information", key: "push_content", label: "settings.push_content" },
              {
                icon: "mdi-email-send",
                key: "SEND_MAIL_FOR_NEW_BOOKS",
                label: "settings.send_mail_for_new_books",
                type: "checkbox",
              },
            ],
          },
          {
            id: "push-devices",
            icon: "mdi-tablet-cellphone",
            title: "settings.device_mgt",
            desc: "settings.device_mgt_description",
            special: "devices",
          },
        ],
      },
      {
        id: "services",
        icon: "mdi-source-branch",
        title: "settings.group_services",
        sections: [
          {
            id: "svc-meta",
            icon: "mdi-web-sync",
            title: "settings.internet_book_sources",
            tips: [
              {
                text: "settings.douban_plugin_description",
              },
            ],
            fields: [
              {
                icon: "mdi-web-sync",
                key: "auto_fill_meta",
                label: "settings.auto_fill_meta",
                type: "checkbox",
              },
              {
                icon: "mdi-source-branch",
                key: "META_SELECTED_SOURCES",
                label: "settings.meta_selected_source",
                type: "meta_sources",
                al: ["豆瓣", "书源"],
              },
              {
                icon: "mdi-information",
                key: "douban_baseurl",
                label: "settings.douban_baseurl",
              },
              {
                icon: "mdi-information",
                key: "douban_apikey",
                label: "settings.douban_api_key",
              },
              {
                icon: "mdi-information",
                key: "douban_max_count",
                label: "settings.douban_max_count",
              }
            ],
          },
          {
            id: "svc-bookbarn",
            icon: "mdi-key",
            title: "settings.book_barn_service",
            special: "bookbarn",
          },
          {
            id: "svc-ai",
            icon: "mdi-scatter-plot-outline",
            title: "settings.ai_capability",
            special: "ai_capabilities",
          },
        ],
      },
      {
        id: "protocols",
        icon: "mdi-cloud-outline",
        title: "settings.group_protocols",
        sections: [
          {
            id: "proto-webdav",
            icon: "mdi-cloud-check-outline",
            title: "settings.sec_proto_webdav",
            fields: [
              {
                icon: "mdi-cloud-check-outline",
                key: "ENABLE_WEBDAV_SERVICE",
                label: "settings.enable_webdav_service",
                type: "checkbox",
              },
              {
                icon: "mdi-cloud-sync-outline",
                key: "WEBDAV_SYNC_FOLDER",
                label: "settings.enable_webdav_sync",
                type: "checkbox",
              },
            ],
          },
          {
            id: "proto-opds",
            icon: "mdi-cloud-print-outline",
            title: "settings.sec_proto_opds",
            fields: [
              {
                icon: "mdi-cloud-print-outline",
                key: "ENABLE_OPDS_SERVICE",
                label: "settings.enable_opds_service",
                type: "checkbox",
              },
              {
                icon: "mdi-lock",
                key: "ENABLE_OPDS_AUTH",
                label: "settings.enable_opds_auth",
                type: "checkbox",
              },
            ],
          },
          {
            id: "proto-podcast",
            icon: "mdi-podcast",
            title: "settings.sec_proto_podcast",
            fields: [
              {
                icon: "mdi-podcast",
                key: "ENABLE_PODCAST_SERVICE",
                label: "settings.enable_podcast_service",
                type: "checkbox",
              },
            ],
          },
          {
            id: "proto-net",
            icon: "mdi-lock",
            title: "settings.sec_proto_net",
            fields: [
              { icon: "mdi-home", color: "red", key: "static_host", label: "settings.cdn_domain" },
              {
                icon: "mdi-lock",
                color: "red",
                key: "cookie_secret",
                label: "settings.cookie_secret",
              },
            ],
            special: "ssl",
          },
        ],
      },
      {
        id: "ops",
        icon: "mdi-restart",
        title: "settings.group_ops",
        sections: [
          {
            id: "ops-perf",
            icon: "mdi-speedometer",
            title: "settings.sec_ops_perf",
            special: "perf",
          },
          {
            id: "ops-log",
            icon: "mdi-math-log",
            title: "settings.sec_ops_log",
            fields: [
              {
                icon: "mdi-archive-cog-outline",
                color: "red",
                key: "LOG_LEVEL_DEBUG",
                label: "settings.enable_debug_logging",
                type: "checkbox",
              },
              {
                icon: "mdi-math-log",
                key: "ENABLE_AUDIO_CONVERSION_LOG",
                label: "settings.enable_audio_conversion_log",
                type: "checkbox",
              },
              {
                icon: "mdi-closed-caption-outline",
                key: "ENABLE_AUDIO_SUBTITLE",
                label: "settings.enable_audio_subtitle",
                type: "checkbox",
              },
              {
                icon: "mdi-restart",
                key: "autoreload",
                label: "settings.autoreload",
                type: "checkbox",
              },
              {
                icon: "mdi-information",
                key: "convert_timeout",
                label: "settings.convert_timeout",
              },
            ],
          },
          {
            id: "ops-update",
            icon: "mdi-update",
            title: "settings.sec_ops_update",
            fields: [
              {
                icon: "mdi-update",
                key: "AUTO_CHECKING_NEW_VERSION",
                label: "settings.auto_checking_new_version",
                type: "checkbox",
              },
              {
                icon: "mdi-toolbox-outline",
                key: "ENABLE_TOOLBOX_DEV_MODE",
                label: "settings.enable_toolbox_dev_mode",
                type: "checkbox",
              },
              {
                icon: "mdi-storefront-outline",
                key: "ENABLE_TOOLBOX_STORE",
                label: "settings.enable_toolbox_store",
                type: "checkbox",
              },
            ],
          },
          {
            id: "ops-trash",
            icon: "mdi-delete",
            title: "settings.trash_management",
            special: "trash",
          },
        ],
      },
    ];

    this.$backend("/admin/settings").then((rsp) => {
      this.sns_items = rsp.sns;
      this.settings = rsp.settings;
      this.site_url = rsp.site_url;

      if (this.settings) {
        if (this.settings["site_language"] === "") {
          this.settings["site_language"] = this.$i18n.locale;
        }
        if (
          !("site_icon" in this.settings) ||
          this.settings["site_icon"] === ""
        ) {
          this.settings["site_icon"] = "favicon_0";
        }
        if (!Array.isArray(this.settings["READER_MYDICTS"])) {
          this.$set(this.settings, "READER_MYDICTS", []);
        }
        for (const key of ["READER_DICT_MYBOOKS_ENABLED", "READER_DICT_BAIKE_ENABLED"]) {
          if (typeof this.settings[key] !== "boolean") this.$set(this.settings, key, true);
        }
        if (
          !("DEVICES" in this.settings) ||
          !Array.isArray(this.settings["DEVICES"])
        ) {
          this.settings["DEVICES"] = [];
        }
        if (
          !("META_SELECTED_SOURCES" in this.settings) ||
          !Array.isArray(this.settings["META_SELECTED_SOURCES"])
        ) {
          this.settings["META_SELECTED_SOURCES"] = (
            this.settings["META_ALL_SOURCES"] || [
              "douban",
              "baidu",
              "google",
              "amazon",
              "xinhua",
              "youshu",
              "ujxsw"
            ]
          ).slice();
        }
        if (process.client && this.settings["MAX_UPLOAD_SIZE"] !== "") {
          localStorage.setItem(
            "max_upload_size",
            this.settings["MAX_UPLOAD_SIZE"]
          );
        }
        if (process.client && this.settings["CHUNK_UPLOAD_SIZE"] !== "") {
          localStorage.setItem(
            "chunk_upload_size",
            this.settings["CHUNK_UPLOAD_SIZE"]
          );
        }
        var m = {};
        rsp.sns.forEach(function (ele) {
          m[ele.value] = ele;
        });
        this.settings.SOCIALS.forEach(function (ele) {
          ele.help = false;
          ele.link = m[ele.value].link;
        });

        this.bookNavList = this.parseBookNav(this.settings["BOOK_NAV"] || "");
        this.snapshot = JSON.parse(JSON.stringify(this.settings));
        this.bookNavSnapshot = JSON.parse(JSON.stringify(this.bookNavList));
        this.settingsLoaded = true;
      }
    });
  },
  data: () => ({
    combo_input: "",
    sns: {},
    sns_items: [],
    settings: {},
    settingsLoaded: false,
    snapshot: {},
    bookNavSnapshot: [],
    savingDefaultReadRange: false,
    site_url: "",
    groups: [],
    activeGroup: "site",
    searchQ: "",
    // 搜索框是否展开（收起态只显示放大镜图标，点开才出现输入框）
    searchOpen: false,
    // 搜索跳转的视图层展开状态（key = 嵌套开关 grp.key），不触碰真实设置值
    forceOpen: {},
    bookNavList: [],
    thanksToNames: [],
    thanksToShow: false,
    appliedToken: false,
    testingConnection: false,
    testingAI: false,
    deviceTypes: [],
    deviceSchemas: [
      { text: "HTTP", value: "http" },
      { text: "HTTPS", value: "https" },
    ],
    trashSizes: { trash: 0, upload: 0 },
    trashSizeTexts: { trash: "", upload: "" },
    trashLoading: false,
    trashConfirmDialog: false,
    saveConfirmDialog: false,
    restartConfirmDialog: false,
    stampPreviewUrl: "",
    stampPositions: [
      { value: "top-left", icon: "mdi-format-align-top" },
      { value: "top-center", icon: "mdi-format-align-top" },
      { value: "top-right", icon: "mdi-format-align-top" },
      { value: "center-left", icon: "mdi-format-align-middle" },
      { value: "center", icon: "mdi-format-align-middle" },
      { value: "center-right", icon: "mdi-format-align-middle" },
      { value: "bottom-left", icon: "mdi-format-align-bottom" },
      { value: "bottom-center", icon: "mdi-format-align-bottom" },
      { value: "bottom-right", icon: "mdi-format-align-bottom" },
    ],
  }),
  computed: {
    currentGroups() {
      return this.groups.filter((g) => g.id === this.activeGroup);
    },
    searchQuery() {
      return (this.searchQ || "").trim();
    },
    dirtyCount() {
      if (!this.settingsLoaded) return 0;
      const before = this.snapshot;
      const now = this.settings;
      // READER_MYDICTS 元素上的 showToken 只是显隐 token 的视图状态，
      // 点眼睛图标不应算作未保存修改，比较前先剥掉
      const stripView = (k, v) =>
        k === "READER_MYDICTS" && Array.isArray(v)
          ? v.map((d) => {
              const e = { ...d };
              delete e.showToken;
              return e;
            })
          : v;
      let n = 0;
      Object.keys(now).forEach((k) => {
        if (JSON.stringify(stripView(k, before[k])) !== JSON.stringify(stripView(k, now[k]))) n++;
      });
      if (JSON.stringify(this.bookNavSnapshot) !== JSON.stringify(this.bookNavList)) n++;
      return n;
    },
    flatIndex() {
      const idx = [];
      const pathOf = {};
      this.groups.forEach((g) => {
        g.sections.forEach((s) => {
          pathOf[g.id + "/" + s.id] =
            this.$t(g.title) + " / " + this.$t(s.title);
        });
      });
      const push = (entry, gid, sid, extraPath, parentKey) => {
        idx.push({
          key: entry.key,
          label: this.$t(entry.label),
          icon: entry.icon || "",
          red: entry.color === "red",
          gid,
          sid,
          path: pathOf[gid + "/" + sid] + (extraPath ? " / " + extraPath : ""),
          al: entry.al || [],
          parentKey: parentKey || "",
        });
      };
      this.groups.forEach((g) => {
        g.sections.forEach((s) => {
          (s.fields || []).forEach((f) => push(f, g.id, s.id, ""));
          (s.groups || []).forEach((grp) => {
            push(grp, g.id, s.id, "");
            (grp.fields || []).forEach((f) =>
              push(f, g.id, s.id, this.$t(grp.label), grp.key)
            );
          });
        });
      });
      SPECIAL_BLOCKS.forEach((b) => {
        idx.push({
          key: b.key,
          label: this.$t(b.label),
          icon: b.icon,
          red: false,
          gid: b.gid,
          sid: b.sid,
          path: pathOf[b.gid + "/" + b.sid],
          al: b.al || [],
        });
      });
      return idx;
    },
    results() {
      const q = (this.searchQ || "").trim().toLowerCase();
      if (!q) return [];
      const tokens = q.split(/\s+/);
      const aliasSets = tokens.map((t) => SEARCH_ALIASES[t] || []);
      const out = [];
      this.flatIndex.forEach((r) => {
        const label = r.label.toLowerCase();
        const key = r.key.toLowerCase();
        const aliasText = r.al.join(" ").toLowerCase();
        let total = 0;
        for (let i = 0; i < tokens.length; i++) {
          const t = tokens[i];
          let best = 0;
          if (aliasSets[i].indexOf(r.key) >= 0) best = 82;
          if (label.indexOf(t) >= 0) best = Math.max(best, t.length >= 2 ? 76 : 55);
          if (key.indexOf(t) >= 0) best = Math.max(best, 60);
          if (aliasText.indexOf(t) >= 0) best = Math.max(best, 64);
          if (best === 0) {
            total = 0;
            break;
          }
          total += best;
        }
        if (total > 0) out.push(Object.assign({ score: total }, r));
      });
      out.sort((a, b) => b.score - a.score);
      return out;
    },
    liteGroups() {
      return LITE_GROUPS;
    },
    thumbCache: {
      get() {
        return this.settings["THUMB_CACHE"] !== false;
      },
      set(value) {
        this.$set(this.settings, "THUMB_CACHE", value);
      },
    },
    cacheMaxMb: {
      get() {
        return Number(this.settings["CACHE_MAX_MB"]) || 200;
      },
      set(value) {
        this.$set(this.settings, "CACHE_MAX_MB", value);
      },
    },
    cacheSizeItems() {
      return [50, 100, 200, 300].map((v) => ({ text: v + " MB", value: v }));
    },
    liteMode: {
      get() {
        return this.settings["PERFORMANCE_MODE"] === "lite";
      },
      set(value) {
        this.$set(this.settings, "PERFORMANCE_MODE", value ? "lite" : "normal");
      },
    },
    urlRule() {
      return (v) => {
        if (!v) return true;
        const pattern = /^https?:\/\/.+/;
        return pattern.test(v) || this.$t('settings.url_rule_error');
      };
    },
    modelNameRule() {
      return (v) => {
        if (!v) return true;
        const pattern = /^(?![.\-/:])[a-zA-Z0-9]+(?:[_.\-/:][a-zA-Z0-9]+)*$/;
        return pattern.test(v) || this.$t('settings.model_name_rule_error');
      };
    },
    apiKeyRules() {
      return [
        (v) => !v || /^[a-zA-Z0-9-._]*$/.test(v) || this.$t('settings.api_key_rule_error'),
        (v) => !v || (v.length >= 16 && v.length <= 128) || this.$t('settings.api_key_length_error'),
      ];
    },
    metaSourceItems() {
      const allSources = this.settings["META_ALL_SOURCES"] || [
        "douban",
        "baidu",
        "google",
        "amazon",
        "xinhua",
        "youshu",
        "douban_v2",
        "ujxsw"
      ];
      return allSources.map((source) => ({
        text: this.$t("settings.meta_source_" + source),
        value: source,
      }));
    },
    saveConfirmMessage() {
      return this.settings["autoreload"]
        ? this.$t("settings.save_confirm_message_autoreload")
        : this.$t("settings.save_confirm_message_no_autoreload");
    },
    bookNavDuplicateNames() {
      const counts = {};
      this.bookNavList.forEach((cat) => {
        const name = (cat.name || "").trim();
        if (!name) return;
        counts[name] = (counts[name] || 0) + 1;
      });
      return Object.keys(counts).filter((name) => counts[name] > 1);
    },
    defaultReadRangeSummary() {
      const range = this.settings["DEFAULT_READ_RANGE"] || {};
      const mode = range.mode || 0;
      if (mode === 0) {
        return this.$t("settings.default_read_range_all");
      }
      const categories = range.categories ? range.categories.split(",").filter(Boolean) : [];
      const tags = range.tags ? range.tags.split(",").filter(Boolean) : [];
      const parts = [];
      if (categories.length) {
        parts.push(this.$t("settings.default_read_range_categories_part", { value: categories.join("、") }));
      }
      if (tags.length) {
        parts.push(this.$t("settings.default_read_range_tags_part", { value: tags.join("、") }));
      }
      const list = parts.length ? parts.join("，") : this.$t("settings.default_read_range_unset");
      return mode === 1
        ? this.$t("settings.default_read_range_whitelist", { list })
        : this.$t("settings.default_read_range_blacklist", { list });
    },
  },
  beforeRouteLeave(to, from, next) {
    // 未保存更改的离开守卫：切路由丢配置是本页最需要防的场景
    if (this.dirtyCount > 0 && !window.confirm(this.$t("settings.unsaved_leave_confirm", { n: this.dirtyCount }))) {
      next(false);
      return;
    }
    next();
  },
  mounted() {
    this.fetchTrashSize();
    this.loadStampImage();
    this.loadThanksTo();
    this.updateBarOffset();
    if (process.client) {
      window.addEventListener("resize", this.updateBarOffset);
      window.addEventListener("beforeunload", this.handleBeforeUnload);
      this.watchAppBar();
    }
  },
  beforeDestroy() {
    // 页面销毁时移除settings-page类名
    if (process.client) {
      document.body.classList.remove("settings-page");
      window.removeEventListener("resize", this.updateBarOffset);
      window.removeEventListener("beforeunload", this.handleBeforeUnload);
      // 清掉 documentElement 上的全局 CSS 变量，避免残留值影响其他页面
      document.documentElement.style.removeProperty("--settings-bar-top");
      if (this._barObserver) {
        this._barObserver.disconnect();
        this._barObserver = null;
      }
      if (this._barWatcher) {
        this._barWatcher.disconnect();
        this._barWatcher = null;
      }
    }
  },
  methods: {
    // 全局 AppHeader 由 store.nav 的 v-if 控制渲染，可能晚于本页 mounted；出现后按其真实高度校准吸顶偏移
    watchAppBar() {
      const attach = () => {
        const header = document.querySelector(".v-app-bar");
        if (!header) return false;
        this._barObserver = new ResizeObserver(this.updateBarOffset);
        this._barObserver.observe(header);
        this.updateBarOffset();
        return true;
      };
      if (attach()) return;
      this._barWatcher = new MutationObserver(() => {
        if (attach() && this._barWatcher) {
          this._barWatcher.disconnect();
          this._barWatcher = null;
        }
      });
      this._barWatcher.observe(document.body, { childList: true, subtree: true });
    },
    updateBarOffset() {
      const header = document.querySelector(".v-app-bar");
      const bottom = header ? header.getBoundingClientRect().bottom : 56;
      document.documentElement.style.setProperty(
        "--settings-bar-top",
        Math.max(48, Math.round(bottom)) + "px"
      );
    },
    // 关闭/刷新标签页前的未保存提示（浏览器只允许展示原生文案，无法本地化）
    handleBeforeUnload(e) {
      if (this.dirtyCount > 0) {
        e.preventDefault();
        e.returnValue = "";
      }
    },
    // 入参保留分组 id（调用侧 groupAccent(g.id) 不变），色值当前统一取站点主色 accent
    groupAccent(_id) {
      const ap = this.$store && this.$store.state && this.$store.state.appearance;
      const a = ap && ap.accent;
      return isHexColor(a) ? a.toLowerCase() : DEFAULT_ACCENT;
    },
    openSearch() {
      this.searchOpen = true;
      this.$nextTick(() => {
        const f = this.$refs.searchField;
        if (f && f.focus) f.focus();
      });
    },
    closeSearch() {
      this.searchQ = "";
      this.searchOpen = false;
    },
    onSearchBlur() {
      // 失焦且输入为空时自动收起；有输入时保持展开，方便点选搜索结果
      if (!this.searchQuery) this.searchOpen = false;
    },
    selectGroup(id) {
      this.searchQ = "";
      this.searchOpen = false;
      this.activeGroup = id;
      if (process.client) window.scrollTo({ top: 0 });
    },
    jumpTo(r) {
      this.searchQ = "";
      this.searchOpen = false;
      this.activeGroup = r.gid;
      if (r.parentKey) {
        // 只做视图层展开：写真实 settings 会静默开启 INVITE_MODE 等父开关并计入未保存数
        this.$set(this.forceOpen, r.parentKey, true);
      }
      if (!process.client) return;
      this.$nextTick(() => {
        setTimeout(() => {
          const el =
            document.getElementById("f-" + r.key) ||
            document.getElementById("sec-" + r.gid + "-" + r.sid);
          if (!el) return;
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.classList.remove("field-flash");
          void el.offsetWidth;
          el.classList.add("field-flash");
        }, 100);
      });
    },
    openDefaultReadRangeDialog() {
      const range = this.settings["DEFAULT_READ_RANGE"] || {};
      this.$refs.defaultReadRangeDialog.open({
        mode: range.mode || 0,
        categories: range.categories || "",
        tags: range.tags || "",
      });
    },
    saveDefaultReadRange(range) {
      const defaultReadRange = {
        mode: range.mode,
        categories: range.categories,
        tags: range.tags,
      };
      this.savingDefaultReadRange = true;
      this.$backend("/admin/settings", {
        method: "POST",
        body: JSON.stringify({DEFAULT_READ_RANGE: defaultReadRange }),
      }).then((rsp) => {
        if (rsp.err !== "ok") {
          this.$alert("error", rsp.msg || this.$t("settings.save_error"));
          return;
        }
        this.$set(this.settings, "DEFAULT_READ_RANGE", defaultReadRange);
        this.$set(this.snapshot, "DEFAULT_READ_RANGE", JSON.parse(JSON.stringify(defaultReadRange)));
        this.$refs.defaultReadRangeDialog.close();
        this.$alert("success", rsp.msg || this.$t("settings.save_success"));
      }).finally(() => {
        this.savingDefaultReadRange = false;
      });
    },
    async loadThanksTo() {
      try {
        const rsp = await this.$backend("/admin/thanks/notes");
        if (rsp.err === "ok") {
          this.thanksToNames = rsp.names || [];
        }
      } catch (error) {
        console.warn("Failed to load thanks-to list:", error);
      }
    },
    parseBookNav(text) {
      const list = [];
      (text || "").split("\n").forEach((line) => {
        if (!line.trim()) return;
        const idx = line.indexOf("=");
        let name = line;
        let tags = [];
        if (idx !== -1) {
          name = line.slice(0, idx);
          tags = line
            .slice(idx + 1)
            .split("/")
            .map((t) => t.trim())
            .filter((t) => t !== "");
        }
        list.push(createCategory(name.trim(), tags));
      });
      return list;
    },
    serializeBookNav(list) {
      return list
        .filter((cat) => (cat.name || "").trim() !== "")
        .map((cat) => `${cat.name.trim()}=${(cat.tags || []).join("/")}`)
        .join("\n");
    },
    saveSettings: function () {
      if (this.bookNavDuplicateNames.length > 0) {
        this.$alert(
          "error",
          this.$t("settings.book_nav_duplicate_error", {
            names: this.bookNavDuplicateNames.join("、"),
          })
        );
        return;
      }
      // 规范化只作用于提交副本：BOOK_NAV 的 parse→serialize 往返不恒等，
      // 若先改写 live settings，保存失败会留下用户没动过的假 diff 且无自愈出口
      const payload = JSON.parse(JSON.stringify(this.settings));
      payload["BOOK_NAV"] = this.serializeBookNav(this.bookNavList);
      // showToken is view state only; the server drops incomplete entries.
      payload["READER_MYDICTS"] = (payload["READER_MYDICTS"] || []).map((dict) => {
        const entry = { ...dict };
        delete entry.showToken;
        return entry;
      });

      if (payload["site_language"] === "") {
        payload["site_language"] = "zh";
      }

      // 快照取提交时刻的值：保存期间的新编辑不会被视为已持久化
      const savedSnapshot = JSON.parse(JSON.stringify(payload));
      const savedNav = JSON.parse(JSON.stringify(this.bookNavList));
      this.$backend("/admin/settings", {
        method: "POST",
        body: JSON.stringify(payload),
      }).then((rsp) => {
        if (rsp.err != "ok") {
          this.$alert("error", rsp.msg || this.$t("settings.save_error"));
          return;
        }
        // 服务端确认后才把规范化结果落到本地状态与 localStorage
        this.settings["BOOK_NAV"] = payload["BOOK_NAV"];
        this.settings["READER_MYDICTS"] = payload["READER_MYDICTS"];
        this.settings["site_language"] = payload["site_language"];
        if (this.settings["site_language"] !== "") {
          this.$i18n.locale = this.settings["site_language"];
        }
        if (process.client) {
          if (this.settings["MAX_UPLOAD_SIZE"] !== "") {
            localStorage.setItem(
              "max_upload_size",
              this.settings["MAX_UPLOAD_SIZE"]
            );
          }

          if (this.settings["CHUNK_UPLOAD_SIZE"] !== "") {
            localStorage.setItem(
              "chunk_upload_size",
              this.settings["CHUNK_UPLOAD_SIZE"]
            );
          }

          localStorage.setItem("indexPage", this.settings["INDEX_PAGE_TYPE"]);
          localStorage.setItem("aiEnabled", this.settings["AI_ENABLED"]);
          localStorage.setItem(
            "defaultPageSize",
            this.settings["DEFAULT_PAGE_SIZE"]
          );
        }
        this.snapshot = savedSnapshot;
        this.bookNavSnapshot = savedNav;
        this.$alert("success", rsp.msg || this.$t("settings.save_success"));
      });
    },
    restartServer: function () {
      this.restartConfirmDialog = false;
      this.$backend("/admin/restart", {
        method: "POST",
      }).then((rsp) => {
        if (rsp.err != "ok") {
          this.$alert("error", rsp.msg || this.$t("settings.restart_error"));
        } else {
          this.$alert("success", rsp.msg || this.$t("settings.restart_success"));
        }
      });
    },
    showSNSConfig: function (s) {
      var msg = `${this.$t("settings.sns_config_message", {
        text: s.text,
        link: s.link,
        site_url: this.site_url,
        value: s.value,
      })}`;
      this.$alert("warning", msg);
    },
    applyBookbarnToken() {
      this.appliedToken = true;
      this.$backend("/admin/bookbarn/token/apply", {
        method: "POST",
        body: JSON.stringify(this.settings),
      }).then((rsp) => {
        if (rsp.err != "ok") {
          this.appliedToken = false;
          this.$alert("error", rsp.msg);
        } else {
          this.$alert("success", rsp.msg);
          this.settings["BOOKBARN_TOKEN"] = rsp.token;
        }
      });
    },
    testEmail: function () {
      var data = new URLSearchParams();
      data.append("smtp_server", this.settings["smtp_server"]);
      data.append("smtp_username", this.settings["smtp_username"]);
      data.append("smtp_password", this.settings["smtp_password"]);
      data.append("smtp_encryption", this.settings["smtp_encryption"]);
      this.$backend("/admin/testmail", {
        method: "POST",
        body: data,
      }).then((rsp) => {
        if (rsp.err != "ok") {
          this.$alert("error", rsp.msg);
        } else {
          this.$alert("success", rsp.msg);
        }
      });
    },
    run: function (func) {
      this[func]();
    },
    generateMCPToken: function () {
      // Call backend API to generate token
      this.$backend("/admin/token")
        .then((rsp) => {
          if (rsp.err !== "ok") {
            this.$alert(
              "error",
              this.$t("settings.ai_mcp_token_generate_failed")
            );
          } else {
            this.settings["AI_MCP_TOKEN"] = rsp.token;
            this.$alert("success", this.$t("settings.ai_mcp_token_generated"));
          }
        })
        .catch((_err) => {
          this.$alert(
            "error",
            this.$t("settings.ai_mcp_token_generate_failed")
          );
        });
    },
    fetchTrashSize() {
      this.trashLoading = true;
      this.$backend("/admin/trash/size").then((rsp) => {
        this.trashLoading = false;
        if (rsp && rsp.err === "ok" && rsp.sizes) {
          this.trashSizes = rsp.sizes;
          this.trashSizeTexts = {
            trash: this.formatTrashSize(rsp.sizes.trash),
            upload: this.formatTrashSize(rsp.sizes.upload),
          };
        } else {
          this.trashSizeTexts = {
            trash: this.$t("settings.trash_unknown"),
            upload: this.$t("settings.trash_unknown"),
          };
        }
      });
    },
    formatTrashSize(size) {
      if (size < 1024) return size + " B";
      if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KB";
      if (size < 1024 * 1024 * 1024)
        return (size / 1024 / 1024).toFixed(2) + " MB";
      return (size / 1024 / 1024 / 1024).toFixed(2) + " GB";
    },
    clearTrash() {
      this.trashConfirmDialog = false;
      this.$backend("/admin/trash/clear", {
        method: "POST",
      }).then((rsp) => {
        if (rsp && rsp.err === "ok") {
          this.$alert("success", rsp.msg);
          this.fetchTrashSize();
        } else {
          this.$alert("error", rsp.msg);
        }
      });
    },
    uploadStampImage(event) {
      const file = event.target.files[0];
      if (!file) return;

      // 验证文件类型
      if (file.type !== 'image/png') {
        this.$alert("error", this.$t('settings.stamp_image_format_error'));
        return;
      }

      // 验证文件大小
      const maxSize = 128 * 1024; // 128KB
      if (file.size > maxSize) {
        this.$alert("error", this.$t('settings.stamp_image_size_error'));
        return;
      }

      // 验证图片尺寸
      const img = new Image();
      const reader = new FileReader();

      reader.onload = (e) => {
        img.onload = () => {
          if (img.width > 480 || img.height > 480) {
            this.$alert("error", this.$t('settings.stamp_image_dimension_error'));
            return;
          }

          // 验证通过，上传图片
          const formData = new FormData();
          formData.append('file', file);

          this.$backend("/admin/stamp", {
            method: "POST",
            body: formData,
          }).then((rsp) => {
            if (rsp.err === "ok") {
              this.$alert("success", this.$t('settings.stamp_upload_success'));
              this.loadStampImage();
            } else {
              this.$alert("error", rsp.msg);
            }
          });
        };
        img.src = e.target.result;
      };

      reader.readAsDataURL(file);
    },
    loadStampImage() {
      // 加载图章预览图片
      const timestamp = new Date().getTime();
      this.stampPreviewUrl = `${this.site_url}/logo/stamp.png?t=${timestamp}`;
    },
    openStampFileDialog() {
      // 处理ref可能是数组的情况（在v-for中）
      const input = this.$refs.stampFileInput;
      if (input) {
        const element = Array.isArray(input) ? input[0] : input;
        if (element && typeof element.click === 'function') {
          element.click();
        }
      }
    },
    testAISettings() {
      const data = {
        api_url: this.settings['AI_API_URL'],
        api_key: this.settings['AI_DEEPSEEK_API_KEY'],
        api_model: this.settings['AI_MODEL'],
      };
      this.testingAI = true;
      this.$backend("/admin/ai/test", {
        method: "POST",
        body: JSON.stringify(data)
      }).then((rsp) => {
        if (rsp && rsp.err === "ok") {
          this.$alert("success", rsp.msg);
        } else {
          this.$alert("error", rsp.msg);
        }
      }).catch((err) => {
        this.$alert("error", err.message || this.$t("settings.test_ai_failed"));
      }).finally(() => {
        this.testingAI = false;
      });
    },
  },
};
</script>

<style>
.cursor-pointer {
  cursor: pointer;
}

/* 页内吸顶分组条：top 动态取全局 v-app-bar 实际底边（mounted 时测量写入 CSS 变量，
   xs 端 AppHeader 的搜索扩展行有无会导致高度在 48~120px 间变化，不能硬编码） */
.settings-group-bar {
  position: sticky;
  top: var(--settings-bar-top, 56px);
  z-index: 5;
  padding: 10px 12px 8px;
  margin-bottom: 12px;
}
.settings-group-bar-row {
  gap: 10px;
  flex-wrap: wrap;
}
/* iOS 分段式分组条（形态借鉴 uiverse Zanina 分段 tab，样式为本仓 clean-room 实现）：
   灰底容器 + 激活项高亮 + 品牌主色条；8 个按钮均分整行，圆角跟随 --app-radius
  （与右上角外观菜单的按钮圆角同一变量） */
.settings-seg {
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  flex: 1 1 auto;
  gap: 2px;
  min-width: 0;
  background: #e8e8e8;
  border-radius: var(--app-radius, 4px);
  padding: 4px;
}
.settings-seg-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  gap: 4px;
  border: 0;
  background: transparent;
  border-radius: var(--app-radius, 4px);
  padding: 6px 8px 9px;
  font-size: 13px;
  line-height: 1.4;
  color: inherit;
  cursor: pointer;
  white-space: nowrap;
}
.settings-seg-btn:hover {
  background: rgba(0, 0, 0, 0.06);
}
.settings-seg-btn.is-active {
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  font-weight: 500;
}
.settings-seg-btn:focus-visible {
  outline: 2px solid #1976d2;
  outline-offset: 1px;
}
.settings-seg-btn .v-icon {
  margin-right: 2px;
}
/* 激活项下方品牌主色条（与组标题竖条同色呼应） */
.settings-seg-bar {
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: 3px;
  height: 3px;
  border-radius: 2px;
  opacity: 0;
}
.settings-seg-btn.is-active .settings-seg-bar {
  opacity: 1;
}
/* 组标题左侧竖条，与 pill 色条同色 */
.settings-group-title-bar {
  width: 4px;
  align-self: stretch;
  min-height: 36px;
  border-radius: 2px;
  margin-right: 2px;
}
.theme--dark .settings-seg {
  background: #2b2b2b;
}
.theme--dark .settings-seg-btn:hover {
  background: rgba(255, 255, 255, 0.08);
}
.theme--dark .settings-seg-btn.is-active {
  background: #424242;
}
/* 右侧：状态 chip + 搜索图标/展开框 */
.settings-bar-right {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  flex: 0 0 auto;
}
.settings-status-chip {
  position: static;
  transform: none;
  flex: 0 0 auto;
}
.settings-search-btn {
  flex: 0 0 auto;
}
.settings-group-bar .settings-search-expanded {
  flex: 0 1 260px;
  margin: 0;
}
.settings-search .v-input__slot,
.settings-search fieldset {
  border-radius: 9999px !important;
}
@media (max-width: 599.98px) {
  /* 窄屏：分段条独占一行，4 列 × 2 行仍保持均分；右侧控件另起一行靠右；
     展开的搜索框占满整行 */
  .settings-seg {
    flex: 1 1 100%;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .settings-bar-right {
    flex: 1 1 100%;
    margin-left: 0;
    justify-content: flex-end;
  }
  .settings-group-bar .settings-search-expanded {
    flex: 1 1 100%;
  }
  /* savebar 换行变高后加厚底部留白，避免遮挡最后几个字段 */
  .settings-page-root {
    padding-bottom: 128px;
  }
}
.settings-result {
  border-bottom: 1px solid #eee;
  cursor: pointer;
}
/* 含 half 字段的小节：half 项两列排布（对标 checkbox_list 的 sm=6），其余项独占整行 */
.settings-fields-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 16px;
  align-items: start;
}
.settings-fields-2col > div:not(.settings-field-half) {
  grid-column: 1 / -1;
}
@media (max-width: 599.98px) {
  .settings-fields-2col {
    grid-template-columns: 1fr;
  }
}
.settings-result:hover,
.settings-result:focus {
  background: #f5f5f5;
  outline: none;
}
.theme--dark .settings-result {
  border-bottom-color: #424242;
}
.theme--dark .settings-result:hover,
.theme--dark .settings-result:focus {
  background: #303030;
}
[id^="f-"],
[id^="sec-"] {
  scroll-margin-top: calc(var(--settings-bar-top, 56px) + 110px);
}
@keyframes field-flash {
  0% {
    background: #fff59d;
  }
  100% {
    background: transparent;
  }
}
.field-flash {
  animation: field-flash 1.4s ease-out 2;
  border-radius: 6px;
}
.settings-savebar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  /* 窄屏计数位数大时允许换行，避免横排溢出 */
  flex-wrap: wrap;
  min-height: 56px;
  padding: 8px 24px;
  background: #fff;
  border-top: 1px solid #e0e0e0;
}
.theme--dark .settings-savebar {
  background: #1e1e1e;
  border-top-color: #424242;
}
.settings-page-root {
  padding-bottom: 80px;
}
.settings-page-root .v-card {
  border-radius: 16px;
}

/* 设置页提示按钮 - 自定义背景色 + 大圆角，覆盖 Vuetify 默认样式 */
.settings-hint-btn,
.settings-hint-btn.v-btn--flat,
.settings-hint-btn.v-btn--is-elevated,
.settings-hint-btn:not(.v-btn--text):not(.v-btn--outlined) {
  background-color: #003153 !important;
  background: #003153 !important;
  border-radius: 9999px !important;
  -webkit-border-radius: 9999px !important;
  border-color: #003153 !important;
  color: #ffffff !important;
  padding-left: 24px !important;
  padding-right: 24px !important;
  box-shadow: none !important;
  min-height: 36px !important;
  height: 36px !important;
  overflow: hidden !important;
}

/* 覆盖 Vuetify v-btn 内部伪元素背景层（其默认会生成渐变/着色层叠加在按钮上） */
.settings-hint-btn::before,
.settings-hint-btn::after,
.settings-hint-btn .v-btn__content::before,
.settings-hint-btn .v-btn__content::after {
  background-color: transparent !important;
  background: transparent !important;
  border-radius: 9999px !important;
}

/* 覆盖 Vuetify 按钮背景层（部分版本使用 .v-btn__background / .v-btn__overlay） */
.settings-hint-btn > .v-btn__background,
.settings-hint-btn .v-btn__overlay {
  background-color: transparent !important;
  border-radius: 9999px !important;
}

/* 交互状态也强制使用同样的背景和圆角 */
.settings-hint-btn:hover,
.settings-hint-btn:focus,
.settings-hint-btn:active,
.settings-hint-btn:focus-within,
.settings-hint-btn.is-active {
  background-color: #001e34 !important;
  background: #001e34 !important;
  border-radius: 9999px !important;
  border-color: #001e34 !important;
  color: #ffffff !important;
}

/* 内部图标和文字颜色保持白色 */
.settings-hint-btn .v-btn__content,
.settings-hint-btn .v-btn__content * {
  color: #ffffff !important;
}

.thanks-heart-icon {
  animation: thanks-to-heartbeat 1.2s ease-in-out infinite;
}

@keyframes thanks-to-heartbeat {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.25); }
}

.thanks-to-section {
  position: relative;
  padding: 12px 10px;
  border-radius: 14px;
  background-color: rgba(223, 219, 214, 0.25);
  text-align: center;
  overflow: hidden;
}

.thanks-to-section::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image: url('/static/images/star.svg');
  background-repeat: no-repeat;
  background-position: center;
  background-size: cover;
  opacity: 0.9;
  pointer-events: none;
}

.thanks-to-desc,
.thanks-to-names {
  position: relative;
  z-index: 1;
}

.thanks-to-desc {
  margin-bottom: 8px;
  color: #ff7300;
  font-weight: bold;
}

.thanks-to-names {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
}

.thanks-to-chip {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  background: #005692e0;
  font-size: 13px;
  color: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.device-item {
  border: 1.5px dashed rgba(0, 0, 0, 0.8);
  border-radius: 6px;
  padding: 15px 4px 15px;
}
.theme--dark .device-item {
  border-color: rgba(255, 255, 255, 0.8);
}
</style>
