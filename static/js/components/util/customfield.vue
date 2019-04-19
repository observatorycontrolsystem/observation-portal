<template>
<span>
  <b-form-group
    v-show="$parent.show"
    label-align-sm="right"
    label-cols-sm="5"
    :description="desc"
    :label="label"
    :label-for="field"
  >
    <b-form-input 
      :id="field" 
      :value="value"
      :state="!hasErrors"
      :type="type || `text`"
      @input="update($event)"
      @blur="blur($event)"
    />
    <slot name="inlineButton"></slot>
    <span class="text-danger" v-for="error in errors" :key="error">{{ error }}</span>
  </b-form-group>
  <!-- TODO: This is what is supposed to be displayed for this field when the parent object is collapsed -->
  <span class="collapse-inline" v-show="!$parent.show">
    {{ label }}: <strong>{{ value || '...' }}</strong>
  </span>
</span>
</template>
<script>
  import moment from 'moment';
  import _ from 'lodash';
  import $ from 'jquery';
  import {datetimeFormat} from '../../utils';
  export default {
    props: [
      'value',
      'label', 
      'field', 
      'errors', 
      'type', 
      'desc'
    ],
    mounted: function() {
      var that = this;
      // TODO: The datetimepicker is not working quite right
      if (this.type === 'datetime') {
        $(this.$el).find('input').datetimepicker({
          format: datetimeFormat,
          minDate: moment().subtract(1, 'days'),
          keyBinds: {left: null, right: null, up: null, down: null}
        }).on('dp.change', function(e) {
          that.update(moment(e.date).format(datetimeFormat));
        });
      }
    },
    computed: {
      hasErrors: function() {
        return !_.isEmpty(this.errors);
      }
    },
    methods: {
      update: function(value) {
        this.$emit('input', value);
      },
      blur: function(value) {
        this.$emit('blur', value);
      }
    }
  };
</script>
