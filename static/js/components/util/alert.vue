<template>
  <b-alert
    :variant="alertclass" 
    :show="alertDuration" 
    dismissible
  >
    <slot></slot>
  </b-alert>
</template>
<script>
  export default {
    props: [
      'alertclass',
    ],
    data: function() {
      return {
        alertDuration: 10
      }
    }
  };
</script>
