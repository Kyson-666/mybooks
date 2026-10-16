<template>
    <div class="mynexus-markdown" v-html="renderedContent"></div>
</template>

<script>
import DOMPurify from "dompurify";
import { marked } from "marked";

export default {
    props: {
        content: {
            type: String,
            default: "",
        },
    },
    computed: {
        renderedContent() {
            return DOMPurify.sanitize(marked.parse(this.content || "", { breaks: true, gfm: true }));
        },
    },
};
</script>

<style scoped>
.mynexus-markdown {
    overflow-wrap: anywhere;
    line-height: 1.6;
}

.mynexus-markdown :deep(> :first-child) {
    margin-top: 0;
}

.mynexus-markdown :deep(> :last-child) {
    margin-bottom: 0;
}

.mynexus-markdown :deep(h1),
.mynexus-markdown :deep(h2),
.mynexus-markdown :deep(h3),
.mynexus-markdown :deep(h4) {
    margin: 1rem 0 0.5rem;
    line-height: 1.3;
}

.mynexus-markdown :deep(p) {
    margin: 0.6rem 0;
}

.mynexus-markdown :deep(ul),
.mynexus-markdown :deep(ol) {
    margin: 0.6rem 0;
    padding-left: 1.4rem;
}

.mynexus-markdown :deep(pre),
.mynexus-markdown :deep(table) {
    max-width: 100%;
    overflow-x: auto;
}

.mynexus-markdown :deep(pre) {
    padding: 0.6rem 0.8rem;
    border-radius: 8px;
    background: rgba(128, 128, 128, 0.12);
}

.mynexus-markdown :deep(code) {
    padding: 0.1rem 0.3rem;
    border-radius: 4px;
    background: rgba(128, 128, 128, 0.12);
    font-size: 0.9em;
}
</style>
