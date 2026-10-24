<template>
    <AppDialog
        v-model="internalValue"
        :persistent="false"
        type="action"
        :title="$t('book.reviewDialogTitle')"
        max-width="420"
        :dismiss-label="$t('book.cancel')"
        :confirm-text="$t('book.recommend')"
        :confirm-loading="saving"
        :confirm-disabled="rating === 0"
        @confirm="submit"
    >
                <div class="text-center mb-2">
                    <v-rating
                        v-model="ratingStars"
                        color="yellow accent-4"
                        length="5"
                        dense
                    ></v-rating>
                </div>
                <v-textarea
                    v-model="comment"
                    outlined
                    dense
                    rows="3"
                    auto-grow
                    counter="5000"
                    maxlength="5000"
                    :label="$t('book.reviewCommentLabel')"
                    :placeholder="$t('book.reviewCommentPlaceholder')"
                ></v-textarea>
    </AppDialog>
</template>

<script>
import { toStars, fromStars } from "~/utils/rating";

export default {
    props: {
        value: {
            type: Boolean,
            default: false,
        },
        bookId: {
            type: [Number, String],
            required: true,
        },
    },
    data() {
        return {
            rating: 8,
            comment: "",
            saving: false,
            loading: false,
        };
    },
    computed: {
        internalValue: {
            get() {
                return this.value;
            },
            set(v) {
                this.$emit("input", v);
            },
        },
        ratingStars: {
            get() {
                return toStars(this.rating);
            },
            set(stars) {
                this.rating = fromStars(stars);
            },
        },
    },
    watch: {
        value(opened) {
            if (opened) {
                this.loadOwnReview();
            }
        },
    },
    methods: {
        async loadOwnReview() {
            this.loading = true;
            try {
                const rsp = await this.$backend(`/book/${this.bookId}/review`);
                if (rsp.err === "ok" && rsp.review) {
                    this.rating = rsp.review.rating || 0;
                    this.comment = rsp.review.comment || "";
                } else {
                    // 新评论默认 4 星（对应后端 0-10 分制的 8 分），减少用户还要先点一下评分的操作
                    this.rating = 8;
                    this.comment = "";
                }
            } catch (e) {
                // 预填充失败不阻塞用户直接打分，静默忽略
            } finally {
                this.loading = false;
            }
        },
        close() {
            this.internalValue = false;
        },
        async submit() {
            if (this.saving || this.rating === 0) return;
            this.saving = true;
            try {
                const rsp = await this.$backend(`/book/${this.bookId}/review`, {
                    method: "POST",
                    body: JSON.stringify({ rating: this.rating, comment: this.comment }),
                });
                if (rsp.err === "ok") {
                    this.$alert("success", rsp.msg || this.$t("book.reviewSaved"));
                    this.$emit("saved", rsp.review);
                    this.close();
                } else {
                    this.$alert("error", rsp.msg || this.$t("message.operationFailed"));
                }
            } catch (e) {
                this.$alert("error", this.$t("message.networkError"));
            } finally {
                this.saving = false;
            }
        },
    },
};
</script>
