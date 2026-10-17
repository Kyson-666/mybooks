<template>
    <AppDialog
        :value="open"
        @input="$emit('update:open', $event)"
        type="action"
        :title="$t('book.sendToDevice')"
        icon="mdi-devices"
        max-width="600"
        :confirm-text="$t('common.send')"
        :confirm-loading="sending"
        :confirm-disabled="!canSendToDevice"
        @dismiss="$emit('dismiss')"
        @confirm="handleConfirm"
    >
        <p class="mb-4">
            {{ $t('book.selectDevice') }}:
            <span class="caption grey--text">
                ({{ $t('message.willSendFormat', { format: selectedFormat }) }})
            </span>
        </p>
        <v-radio-group v-model="selectedDeviceOption">
            <v-radio
                v-for="(device, idx) in devices"
                :key="'device-' + idx"
                :value="'saved-' + idx"
            >
                <template v-slot:label>
                    <span v-if="device.type === 'kindle'">
                        {{ device.name }} ({{ getDeviceTypeText(device.type) }}) - {{ device.mailbox }}
                    </span>
                    <span v-else-if="device.type === 'ftp'">
                        {{ device.name }} ({{ getDeviceTypeText(device.type) }}) - {{ device.ip }}:{{ device.port }} {{ device.ftp_path }}
                    </span>
                    <span v-else>
                        {{ device.name }} ({{ getDeviceTypeText(device.type) }}) - {{ device.ip }}:{{ device.port }}
                    </span>
                </template>
            </v-radio>
            <v-radio
                value="temporary"
                :label="$t('book.temporaryDevice')"
            ></v-radio>
        </v-radio-group>

        <div v-if="selectedDeviceOption === 'temporary'" class="mt-4 pl-8">
            <v-select
                v-model="tempDevice.type"
                :items="deviceTypes"
                :label="$t('book.deviceType') + ' *'"
                outlined
                dense
                :rules="[v => !!v || $t('book.deviceTypeRequired')]"
            ></v-select>

            <template v-if="tempDevice.type === 'kindle'">
                <v-text-field
                    v-model="tempDevice.mailbox"
                    :label="$t('book.kindleMailbox') + ' *'"
                    outlined
                    dense
                    type="email"
                    :rules="[v => !!v || $t('book.kindleMailboxRequired')]"
                    placeholder="user@kindle.com"
                ></v-text-field>
            </template>

            <template v-if="tempDevice.type !== 'kindle'">
                <v-text-field
                    v-model="tempDevice.ip"
                    :label="$t('book.deviceIP') + ' *'"
                    outlined
                    dense
                    :rules="[v => !!v || $t('book.deviceIPRequired')]"
                    placeholder="192.168.1.100"
                ></v-text-field>
                <v-text-field
                    v-model="tempDevice.port"
                    :label="$t('book.devicePort') + ' *'"
                    outlined
                    dense
                    type="number"
                    :rules="[v => !!v || $t('book.devicePortRequired')]"
                    placeholder="21"
                ></v-text-field>
            </template>

            <template v-if="tempDevice.type === 'ftp'">
                <v-text-field
                    v-model="tempDevice.ftp_username"
                    :label="$t('book.ftpUsername')"
                    outlined
                    dense
                    :placeholder="$t('book.ftpAnonymousHint')"
                ></v-text-field>
                <v-text-field
                    v-model="tempDevice.ftp_password"
                    :label="$t('book.ftpPassword')"
                    outlined
                    dense
                    type="password"
                ></v-text-field>
                <v-text-field
                    v-model="tempDevice.ftp_path"
                    :label="$t('book.ftpPath') + ' *'"
                    outlined
                    dense
                    :rules="[v => !!v || $t('book.ftpPathRequired')]"
                    placeholder="/books"
                ></v-text-field>
            </template>
        </div>

        <div v-if="devices.length === 0 && selectedDeviceOption !== 'temporary'" class="text-center py-4">
            <v-icon size="48" color="grey">mdi-help-rhombus-outline</v-icon>
            <p class="mt-2 grey--text">
                {{ $t('book.noDevices') }}<br>
                {{ $t('book.configDeviceDesc') }}
            </p>
        </div>
    </AppDialog>
</template>

<script>
export default {
    name: "SendToDeviceDialog",
    props: {
        open: { type: Boolean, default: false },
        devices: { type: Array, default: () => [] },
        selectedFormat: { type: String, default: "" },
        sending: { type: Boolean, default: false },
    },
    data() {
        return {
            selectedDeviceOption: null,
            tempDevice: {
                type: '',
                ip: '',
                port: '',
                mailbox: '',
                ftp_username: '',
                ftp_password: '',
                ftp_path: '',
            },
        };
    },
    computed: {
        canSendToDevice() {
            if (!this.selectedDeviceOption) return false;
            if (this.selectedDeviceOption === 'temporary') {
                const type = this.tempDevice.type;
                if (type === 'kindle') return !!this.tempDevice.mailbox;
                if (type === 'ftp') return !!(this.tempDevice.ip && this.tempDevice.port && this.tempDevice.ftp_path);
                return !!(this.tempDevice.ip && this.tempDevice.port);
            }
            return !!this.devices;
        },
        deviceTypes() {
            return [
                { text: this.$t('device.duokan'), value: 'duokan' },
                { text: this.$t('device.ireader'), value: 'ireader' },
                { text: this.$t('device.hanwang'), value: 'hanwang' },
                { text: this.$t('device.boox'), value: 'boox' },
                { text: this.$t('device.dangdang'), value: 'dangdang' },
                { text: 'Kindle', value: 'kindle' },
                { text: 'PureLibro', value: 'purelibro' },
                { text: this.$t('device.ftp'), value: 'ftp' },
                { text: this.$t('device.koreader'), value: 'koreader' },
            ];
        },
    },
    watch: {
        open: {
            handler(isOpen) {
                if (!isOpen || !process.client) return;
                this.restoreDevicePreferences();
            },
        },
        tempDevice: {
            handler(newVal) {
                if (process.client) {
                    localStorage.setItem('temp_device_info', JSON.stringify(newVal));
                }
            },
            deep: true,
        },
        'tempDevice.type': function(newType) {
            const portMap = {
                duokan: '12121',
                boox: '8085',
                hanwang: '9310',
                ireader: '10123',
                dangdang: '11111',
                ftp: '21',
                koreader: '80',
            };
            if (portMap[newType]) {
                this.tempDevice.port = portMap[newType];
            }
        },
        selectedDeviceOption: {
            handler(newValue) {
                if (!process.client || !newValue) return;
                try {
                    localStorage.setItem('last_selected_device_option', newValue);
                } catch (error) {
                    console.error('保存设备选项失败:', error);
                }
            }
        }
    },
    methods: {
        restoreDevicePreferences() {
            try {
                const savedOption = localStorage.getItem('last_selected_device_option');
                const savedTempDevice = localStorage.getItem('temp_device_info');
                if (savedOption) {
                    if (savedOption === 'temporary') {
                        this.selectedDeviceOption = savedOption;
                    } else if (savedOption.startsWith('saved-')) {
                        const deviceIndex = parseInt(savedOption.replace('saved-', ''));
                        if (this.devices && this.devices.length > deviceIndex) {
                            this.selectedDeviceOption = savedOption;
                        } else {
                            this.selectedDeviceOption = this.devices && this.devices.length > 0 ? 'saved-0' : 'temporary';
                        }
                    }
                } else {
                    this.selectedDeviceOption = this.devices && this.devices.length > 0 ? 'saved-0' : 'temporary';
                }
                if (savedTempDevice) {
                    const tempDeviceData = JSON.parse(savedTempDevice);
                    this.tempDevice = {
                        type: tempDeviceData.type || '',
                        ip: tempDeviceData.ip || '',
                        port: tempDeviceData.port || '',
                        mailbox: tempDeviceData.mailbox || '',
                        ftp_username: tempDeviceData.ftp_username || '',
                        ftp_password: tempDeviceData.ftp_password || '',
                        ftp_path: tempDeviceData.ftp_path || '',
                    };
                }
            } catch (error) {
                console.error('加载设备偏好设置失败:', error);
                this.selectedDeviceOption = this.devices && this.devices.length > 0 ? 'saved-0' : 'temporary';
            }
        },
        getDeviceTypeText(type) {
            const typeMap = {
                'duokan':   '多看阅读器',
                'ireader':  '掌阅',
                'hanwang':  '汉王',
                'boox':     '文石Boox',
                'dangdang': '当当阅读器',
                'kindle':   'Kindle',
                'purelibro': 'PureLibro',
                'ftp':      'FTP',
                'koreader': 'KoReader',
            };
            return typeMap[type] || type;
        },
        handleConfirm() {
            let deviceInfo;
            let deviceName;
            if (this.selectedDeviceOption === 'temporary') {
                deviceInfo = {
                    type: this.tempDevice.type,
                    ip: this.tempDevice.ip,
                    port: this.tempDevice.port,
                    schema: 'http',
                    mailbox: this.tempDevice.mailbox,
                    ftp_username: this.tempDevice.ftp_username,
                    ftp_password: this.tempDevice.ftp_password,
                    ftp_path: this.tempDevice.ftp_path,
                };
                deviceName = this.$t('book.temporaryDevice');
            } else {
                const deviceIndex = parseInt(this.selectedDeviceOption.replace('saved-', ''));
                deviceInfo = this.devices[deviceIndex];
                deviceName = deviceInfo.name;
            }
            this.$emit('confirm', { deviceInfo, deviceName });
        },
    },
};
</script>
