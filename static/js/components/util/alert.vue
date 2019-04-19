<template>

  <b-alert
    v-if="dismissible"
    dismissible
    :variant="alertclass" 
    :show="alertDuration" 
  >
    <slot></slot>
  </b-alert>
  <b-alert
    v-else
    show 
    :variant="alertclass" 
  >
    <slot></slot>
  </b-alert>

</template>
<script>
  export default {
    props: [
      'alertclass',
      'dismissible'
    ],
    data: function() {
      return {
        alertDuration: 10
      }
    }
  };
</script>
