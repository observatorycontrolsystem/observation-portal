<template>
  <b-container class="p-0">
    <b-form-row :id="id">
      <b-col>
        <b-card no-body>
          <b-card-header class="p-2">
            <b-container class="p-0">
              <b-form-row>
                <b-col class="text-left">
                  <i 
                    class="align-middle mx-2" 
                    :class="icon"
                  />
                  <!-- TODO: The warning and success flicker on page load -->
                  <i 
                    class="fas fa-exclamation-triangle text-danger align-middle" 
                    v-b-tooltip=tooltipConfig 
                    title="Errors in form" 
                    v-show="hasError"
                  />
                  <i 
                    class="fas fa-check text-success align-middle" 
                    v-b-tooltip=tooltipConfig 
                    title="Section is complete" 
                    v-show="!hasError"
                    />
                </b-col>
                <b-col class="text-center">
                  <div>
                    {{ title }} <span v-if="index > 0">#{{ index + 1}}</span>
                  </div>
                </b-col>
                <b-col class="text-right">
                  <b-button 
                    size="sm"
                    v-b-toggle.collapse-1 
                    variant="info"
                    v-b-tooltip=tooltipConfig 
                    :title="show ? 'Minimize' : 'Maximize'" 
                    @click="clickShow" 
                  >
                    <i 
                      class="far" 
                      :class="show ? 'fa-window-minimize' : 'fa-window-maximize'"
                    ></i>
                  </b-button>
                  <b-button 
                    size="sm"
                    class="mx-1"
                    variant="success" 
                    v-show="cancopy" 
                    v-b-tooltip=tooltipConfig 
                    title="Copy" 
                    @click="copy" 
                  >
                    <i class="fa fa-copy fa-fw"></i>
                  </b-button>
                  <b-button 
                    variant="danger" 
                    v-show="canremove" 
                    v-b-tooltip=tooltipConfig 
                    title="Remove" 
                    size="sm"
                    @click="remove" 
                  >
                    <i class="fa fa-trash fa-fw"></i>
                  </b-button>
                </b-col>
              </b-form-row>
            </b-container>
          </b-card-header>
            <b-card-body class="p-3">
              <slot :show="show"></slot>
            </b-card-body>
        </b-card>
      </b-col>
    </b-form-row>
  </b-container>
</template>
<script>
  import _ from 'lodash';

  import { tooltipConfig } from '../../utils.js';
  
  export default {
    props: [
      'id', 
      'errors', 
      'show', 
      'canremove', 
      'cancopy', 
      'icon', 
      'title', 
      'index'
    ],
    data: function() {
      return {
        tooltipConfig: tooltipConfig
      }
    },
    methods:{
      remove: function() {
        if (confirm('Are you sure you want to remove this item?')) {
          this.$emit('remove');
        }
      },
      copy: function() {
        this.$emit('copy');
      },
      clickShow: function() {
        this.$emit('show', !this.show);
      }
    },
    computed:{
      hasError: function() {
        return !_.isEmpty(this.errors);
      }
    }
  };
</script>
