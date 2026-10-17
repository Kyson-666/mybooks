<template>
    <AppDialog
        :value="open"
        @input="$emit('update:open', $event)"
        type="action"
        :title="$t('book.shareToEmail')"
        icon="mdi-email-send"
        max-width="500"
        :confirm-text="$t('common.send')"
        :confirm-loading="sending"
        :confirm-disabled="!canSendToEmail"
        @dismiss="reset"
        @confirm="handleConfirm"
    >
        <p class="mb-4">
            <span v-if="!hasMultipleEmailFormats" class="caption grey--text">
                ({{ $t('book.willSendFormat', { format: selected_email_format.toUpperCase() }) }})
            </span>
        </p>
        <template v-if="hasMultipleEmailFormats">
            <p class="mb-2">{{ $t('book.selectFormatToSend') }}</p>
            <v-radio-group v-model="selected_email_format" class="mt-0">
                <v-radio
                    v-for="file in compatibleFiles"
                    :key="'email-' + file.format"
                    :value="file.format.toLowerCase()"
                    :label="`${file.format} - ${formatFileSize(file.size)}`"
                ></v-radio>
            </v-radio-group>
        </template>
        <p class="mb-4">{{ $t('book.shareToEmailDesc') }}</p>
        <p v-if="lastShareEmail" class="mb-2 body-2">{{ $t('book.emailSourceLabel') }}</p>
        <v-radio-group
            v-if="lastShareEmail"
            v-model="emailSource"
            class="mt-0"
            dense
            hide-details
            @change="fillEmailFromLast"
        >
            <v-radio value="manual" :label="$t('book.emailManualEntry')"></v-radio>
            <v-radio
                value="last"
                :label="$t('book.emailSendToLast') + ' (' + lastShareEmail + ')'"
            ></v-radio>
        </v-radio-group>
        <v-text-field
            v-model="email_address"
            :label="$t('book.emailAddress') + ' *'"
            outlined
            dense
            type="email"
            :rules="emailRules"
            :error-messages="email_error"
            placeholder="example@email.com"
            @input="email_error = ''"
        >
            <template v-slot:prepend-inner>
                <v-icon>mdi-email</v-icon>
            </template>
        </v-text-field>
        <v-alert v-if="email_size_warning" type="warning" dense outlined class="mt-2">
            {{ email_size_warning }}
        </v-alert>
    </AppDialog>
</template>

<script>
export default {
    name: "SendToEmailDialog",
    props: {
        open: { type: Boolean, default: false },
        compatibleFiles: { type: Array, default: () => [] },
        sending: { type: Boolean, default: false },
        lastShareEmail: { type: String, default: "" },
    },
    data() {
        return {
            email_address: '',
            email_error: '',
            email_size_warning: '',
            selected_email_format: '',
            emailSource: 'manual',
        };
    },
    computed: {
        hasMultipleEmailFormats() {
            return this.compatibleFiles.length > 1;
        },
        defaultEmailFormat() {
            const file = this.compatibleFiles[0];
            return file ? file.format.toLowerCase() : '';
        },
        canSendToEmail() {
            return !!(this.email_address && this.isValidEmail(this.email_address) && !this.email_error && this.selected_email_format);
        },
        emailRules() {
            return [
                v => !!v || this.$t('book.emailRequired'),
                v => this.isValidEmail(v) || this.$t('book.emailInvalid')
            ];
        },
    },
    watch: {
        open(val) {
            if (val) {
                this.selected_email_format = this.defaultEmailFormat;
                this.emailSource = 'manual';
                this.email_address = '';
                this.email_error = '';
                this.email_size_warning = '';
            }
        },
    },
    methods: {
        isValidEmail(email) {
            return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email || '');
        },
        formatFileSize(bytes) {
            if (!bytes) return '0 B';
            const units = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(1024));
            return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
        },
        fillEmailFromLast() {
            if (this.emailSource === 'last' && this.lastShareEmail) {
                this.email_address = this.lastShareEmail;
                this.email_error = '';
            } else if (this.emailSource === 'manual' && this.email_address === this.lastShareEmail) {
                this.email_address = '';
            }
        },
        reset() {
            this.email_address = '';
            this.email_error = '';
            this.email_size_warning = '';
            this.selected_email_format = '';
        },
        handleConfirm() {
            if (!this.canSendToEmail) {
                this.$alert('error', this.$t('book.emailRequired'));
                return;
            }
            if (!this.isValidEmail(this.email_address)) {
                this.email_error = this.$t('book.emailInvalid');
                return;
            }
            this.$emit('confirm', { email: this.email_address.trim(), format: this.selected_email_format });
        },
        setWarning(msg) {
            this.email_size_warning = msg;
        },
    },
};
</script>
