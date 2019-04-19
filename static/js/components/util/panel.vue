<template>
  <b-container>
    <b-row :id="id">
      <b-col>
        <b-card no-body>
          <b-card-header>
            <b-container>
              <b-row>
                <b-col class="text-left">
                  <i class="fas" :class="icon"></i>
                  <!-- TODO: The warning and success flicker on page load -->
                  <i class="fas fa-exclamation-triangle text-danger" v-b-tooltip.hover title="Errors in form" v-show="hasError"></i>
                  <i class="fas fa-check text-success" v-b-tooltip.hover title="Section is complete" v-show="!hasError"></i>
                </b-col>
                <b-col class="text-center">
                  <div>
                    {{ title }} <span v-if="index > 0">#{{ index + 1}}</span>
                  </div>
                </b-col>
                <b-col class="text-right">
                  <b-button v-b-toggle.collapse-1 variant="primary" v-on:click="clickShow" v-b-tooltip.hover :title="show ? 'Minimize' : 'Maximize'" size="sm">
                    <i class="fa fa-fw" :class="show ? 'fa-window-minimize' : 'fa-window-maximize'"></i>
                  </b-button>
                  <b-button variant="success" v-on:click="copy" v-show="cancopy" v-b-tooltip.hover title="Copy" size="sm">
                    <i class="fa fa-copy fa-fw"></i>
                  </b-button>
                  <b-button variant="danger" v-on:click="remove" v-show="canremove" v-b-tooltip.hover title="Remove" size="sm">
                    <i class="fa fa-trash fa-fw fa-2x"></i>
                  </b-button>
                </b-col>
              </b-row>
            </b-container>
          </b-card-header>
            <b-card>
              <slot :show="show"></slot>
            </b-card>
        </b-card>
      </b-col>
    </b-row>
  </b-container>
</template>
<script>
  import _ from 'lodash';
  
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
<style>
  /* .panel-body-compact {
    padding-bottom: 5px;
  }

  .panel-heading-compact {
    padding: 5px 15px;
  }

  .panel-title {
    font-size: 1.2em;
    text-align: center;
    height: 30px;
    padding-top: 5px;
  }

  .panel-actions {
    text-align: right;
  }

  .fa-2x {
    vertical-align: middle;
  } */
</style>
