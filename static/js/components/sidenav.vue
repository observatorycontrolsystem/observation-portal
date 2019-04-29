<template>
    <!-- TODO: add the detailed error messages back in -->
  <b-navbar sticky v-b-scrollspy>
    <b-nav-form>
      <b-button-group vertical>
        <div 
          v-b-tooltip=tooltipConfig
          title="Clear form"
        >
          <b-button 
            variant="warning" 
            class="compose-form-button" 
            @click="clear"
          >
            <i class="fa fa-times"></i> 
          </b-button>
        </div>
          <b-dropdown 
            v-if="draftExists" 
            v-b-tooltip=tooltipConfig
            dropleft
            variant="primary" 
            class="compose-form-dropdown" 
            :title="saveDraftTooltipText"
            @click="saveDraft(draftId)" 
          >
            <template slot="button-content">
              <i class="fa fa-save"></i> 
            </template>
            <b-dropdown-item-button @click="saveDraft(false)">
              Save draft #{{ draftId }}
            </b-dropdown-item-button>
            <b-dropdown-item-button @click="saveDraft(true)">
              Save as new draft
            </b-dropdown-item-button>
          </b-dropdown>
          <b-button 
            v-else
            v-b-tooltip=tooltipConfig
            variant="primary" 
            class="compose-form-button" 
            :title="saveDraftTooltipText"
            @click="saveDraft(true)"
          >
            <i class="fa fa-save"></i> 
          </b-button>
        <span 
          v-b-tooltip=tooltipConfig
          title="Submit observing request"
        >
          <b-button 
            variant="success" 
            class="compose-form-button" 
            :disabled="!_.isEmpty(errors)"
            @click="submit" 
          >
            <i class="fa fa-check"></i> 
          </b-button>
        </span>
        <span 
          v-b-tooltip=tooltipConfig
          title="Toggle navigation"
        >
          <b-button 
            v-b-toggle.my-collapse
            class="compose-form-button" 
          >
            <span class="when-opened">
              <i class="fas fa-angle-double-right"></i>
            </span> 
            <span class="when-closed">
              <i class="fas fa-angle-double-left"></i>
            </span>
        </b-button>
        </span>
      </b-button-group>
    </b-nav-form>
    <b-collapse id="my-collapse" visible>
      <hr class="bg-light" style="width:100%; height:1px; border:none;">
      <h6 class="text-secondary text-center">Navigation</h6>
      <b-nav small vertical>
        <b-nav-item href="#general">
          <i 
            v-if="hasRootError" 
            class="fas fa-exclamation-triangle text-danger"
          ></i>
          <i 
            v-else 
            class="fas fa-check text-success"
          ></i>
          General Information
        </b-nav-item>
        <span 
          v-for="(request, requestIndex) in requestgroup.requests" 
          :key="'request' + requestIndex" 
          class="request"
        >
          <b-nav-item :href="'#request' + requestIndex">
            <i 
              v-if="hasError(['requests', requestIndex])" 
              class="fas fa-exclamation-triangle text-danger"
            ></i>
            <i 
              v-else 
              class="fas fa-check text-success"
            ></i>
            Request #{{ requestIndex + 1}}
          </b-nav-item>
          <b-nav vertical>
            <span 
              v-for="(configuration, confIndex) in request.configurations" 
              :key="'configuration' + confIndex"
            >
              <b-nav-item 
                :href="'#configuration' + requestIndex + confIndex" 
                class="nested-once"
              >
                <i 
                  v-if="hasError(['requests', requestIndex, 'configurations', confIndex])" 
                  class="fas fa-exclamation-triangle text-danger"
                ></i>
                <i 
                  v-else 
                  class="fas fa-check text-success"
                ></i>
                Configuration #{{ confIndex + 1 }}
              </b-nav-item>

              <b-nav-item 
                v-for="(instrumentconfig, icIndex) in configuration.instrument_configs" 
                :key="'instrumentconfig' + icIndex" 
                :href="'#instrumentconfig' + requestIndex + confIndex + icIndex" 
                class="nested-twice"
              >
                <i 
                  v-if="hasError(['requests', requestIndex, 'configurations', confIndex, 'instrument_configs', icIndex])" 
                  class="fas fa-exclamation-triangle text-danger"
                ></i>
                <i 
                  v-else 
                  class="fas fa-check text-success"
                ></i>
                Instrument Configuration #{{ icIndex + 1 }}
              </b-nav-item>
              <b-nav-item 
                :href="'#target' + requestIndex + confIndex" 
                class="nested-twice"
              >
                <i 
                  v-if="hasError(['requests', requestIndex, 'configurations', confIndex, 'target'])" 
                  class="fas fa-exclamation-triangle text-danger"
                ></i>
                <i 
                  v-else 
                  class="fas fa-check text-success"
                ></i>
                Target
              </b-nav-item>
              <b-nav-item 
                :href="'#constraints' + requestIndex + confIndex" 
                class="nested-twice"
              >
                <i 
                  v-if="hasError(['requests', requestIndex, 'configurations', confIndex, 'constraints'])" 
                  class="fas fa-exclamation-triangle text-danger"
                ></i>
                <i 
                v-else 
                class="fas fa-check text-success"
              ></i>
                Constraints
              </b-nav-item>
            </span>
            <b-nav-item 
              v-for="(window, windowIndex) in request.windows" 
              :key="'window' + windowIndex" 
              :href="'#window' + requestIndex + windowIndex" 
              class="nested-once"
            >
              <i 
                v-if="hasError(['requests', requestIndex, 'windows', windowIndex])" 
                class="fas fa-exclamation-triangle text-danger"
              ></i>
              <i 
                v-else 
                class="fas fa-check text-success"
              ></i>
              Window #{{ windowIndex + 1 }}
            </b-nav-item>
          </b-nav>
        </span>
      </b-nav>
    </b-collapse>
  </b-navbar>
</template>
<script>
  import _ from 'lodash';

  import { tooltipConfig } from '../utils.js';

  export default {
    props: [
      'requestgroup', 
      'errors',
      'draftId'
    ],
    data: function() {
      return {
        tooltipConfig: tooltipConfig,
        saveDraftTooltipText: 'Save a draft of this observing request. The request will not be submitted.'
      }
    },
    computed: {
      hasRootError: function() {
        return !_.isEmpty(this.errors);
      },
      draftExists: function() {
        return this.draftId > -1;
      }
    },
    methods: {
      getErrors: function(path) {
        return _.get(this.errors, path, []);
      },
      hasError: function(path) {
        return !_.isEmpty(this.getErrors(path));
      },
      saveDraft: function(asNewDraft) {
        let saveId = -1;
        if (!asNewDraft) {
          saveId = this.draftId;
        }
        this.$emit('savedraft', {draftId: saveId});
      },
      submit: function() {
        this.$emit('submit');
      },
      clear: function() {
        this.$emit('clear');
      }
    }
  };
</script>
<style>
  /* The dropdown elements do not receive data-v[hash] attribute applied when using 
    scoped styles, so their styles must be global */

  /* Style the buttons in this component.*/
  .compose-form-button ,
  .compose-form-dropdown button.dropdown-toggle {
      padding: 0;
      font-size: 0.875rem;
      line-height: 1.5;
      border-radius: 0.2rem;
    }
    .compose-form-dropdown ul.dropdown-menu {
      background-color: #000000;
    }
    .compose-form-dropdown ul.dropdown-menu li button.dropdown-item {
      color: #ffffff;
    }
    .compose-form-dropdown ul.dropdown-menu li button.dropdown-item:hover {
      color: #404040;
    }
</style>
<style scoped>
  .form-inline {
    width: 100%;
  }
  .btn-group-vertical {
    width: 100%; 
    display: block;
  }
  /* Display different things on the buttons when the 
  nav is collapsed vs when it is open */
  .collapsed > .when-opened,
  :not(.collapsed) > .when-closed {
    display: none;
  }
  /* Control the nav width for predictability */
  navbar, 
  .nav {
    max-width: 200px;
    min-width: 200px;
    width: 200px;
  }
  /* Stack buttons vertically on top of nav column button, 
  and make sure nav stays under popups */
  nav {
    flex-direction: column;
    z-index: 1;
  }
  /* all links */
  .nav-link {
    color: #999;
    border-left: 2px solid transparent;
  }
  /* active & hover links */
  .active,
  .active:hover,
  .active:focus
  {
    color: #009ec3;
    text-decoration: none;
    background-color: transparent;
    border-left-color: #31b0d5;
  }
  /* Move nested nav items in */
  .nested-once {
    margin-left: 10px;
  }
  .nested-twice {
    margin-left: 20px;
  }
  /* show inactive nested list */
  .request li.active ~ ul.nav {
    display: flex;
  }
  /* hide active nested list */
  .request li ~ ul.nav {
    display: none;
  }
</style>
