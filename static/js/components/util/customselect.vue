<template>
  <span>
    <span class="text-right font-italic extra-help-text">
      <slot name="extra-help-text"/>
    </span>
    <b-form-group
      :id="field + '-fieldgroup-' + $parent.id"
      v-show="$parent.show"
      label-size="sm"
      label-align-sm="right"
      label-cols-sm="4"
      :description="desc"
      :label="label"
      :label-for="field"
    >
      <b-form-select 
        size="sm"
        :id="field + '-select-' + $parent.id" 
        :value="value"
        :state="!hasErrors"
        :options="options"
        @input="update($event)"
      />
      <span 
        class="errors text-danger" 
        v-for="error in errors" 
        :key="error"
      >
        {{ error }}
      </span>    
    </b-form-group>
    <span 
      class="mr-4" 
      v-show="!$parent.show"
    > 
      {{ label }}: <strong>{{ value || '...' }}</strong>
    </span>
  </span>
</template>
<script>
  import _ from 'lodash';

  export default {
    props: [
      'value',
      'label', 
      'field', 
      'options', 
      'errors', 
      'desc'
    ],
    computed: {
      hasErrors: function() {
        return !_.isEmpty(this.errors);
      }
    },
    methods: {
      update: function(value) {
        this.$emit('input', value);
      }
    }
  };
</script>
<style scoped>
  .errors {
    font-size: 80%;
  }
  .extra-help-text {
    font-size: 80%;
  }
</style>
