<template>
  <div class="p-0 text-secondary font-italic data-load-help">
    <transition>
      <span v-if="loadingDataFailed" key="loadFailed">
        Data failed to load
      </span>    
      <span v-else-if="isLoading" key="loading">
        Loading <i class="m-2 fa fa-spin fa-spinner load-spinner"></i>
      </span>
      <span v-else-if="!dataAvailable" key="noDataAvailable">
        No data available for selection
      </span>
    </transition>
  </div>
</template>
<script>
export default {
  props: {
    dataAvailable: {
      type: Boolean,
      required: true
    },
    loadingDataFailed: {
      type: Boolean,
      required: true
    },
    isLoading: {
      type: Boolean,
      required: true
    }
  }
}
</script>
<style scoped>
  .data-load-help {
    line-height: 2rem; /* Vertically center */
  }
</style>
