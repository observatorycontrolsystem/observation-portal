<template>
  <b-modal 
    size="xl"
    :title="header" 
    ref="my-modal" 
  >
    <slot></slot>
    <div slot="modal-footer">
      <b-button
        v-show="showCancel"
        variant="secondary"
        class="float-right m-1"
        @click="close"
      >
        Cancel
      </b-button>
      <b-button
        v-show="showAccept"
        variant="info"
        class="float-right m-1"
        @click="submit"
      >
        Ok
      </b-button>
    </div>
  </b-modal>
</template>
<script>
  export default {
    props: {
      show: Boolean,
      header: String,
      showAccept: {
        type: Boolean,
        default: true
      },
      showCancel: {
        type: Boolean,
        default: true
      }
    },
    mounted: function() {
      if (this.show) {
        this.$refs['my-modal'].show();
      }
    },
    methods: {
      close: function(){
        this.$refs['my-modal'].hide();
        this.$emit('close');
      },
      submit: function(){
        this.$refs['my-modal'].hide();
        this.$emit('submit');
      }
    },
    watch: {
      show: function(value) {
        if (value) {
          this.$refs['my-modal'].show();
        } else {
          this.$refs['my-modal'].hide();
        }
      }
    },
  };
</script>
