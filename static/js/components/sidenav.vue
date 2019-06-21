<template>
    <!-- TODO: add the detailed error messages back in -->
  <b-navbar sticky v-b-scrollspy>
    <b-nav-form>
      <b-button-group 
        vertical 
        size="sm"
      >
        <b-button 
          block
          variant="warning" 
          @click="clear"
        >
          <span v-if="navigationIsExpanded">
            <span class="float-right"><i class="fa fa-times mx-2"></i></span>
            <span class="float-right">Clear Form</span>
          </span>
          <span v-else>
            <i class="fa fa-times mx-2"></i>
          </span>
        </b-button>
        <b-dropdown 
          v-if="draftExists" 
          dropleft
          variant="info" 
          size="sm"
          class="compose-form-dropdown" 
          @click="saveDraft(draftId)" 
        >
          <template v-if="navigationIsExpanded" slot="button-content">
            <span class="float-right">Save Draft # {{ draftId }} <i class="fa fa-save mx-2"></i></span>
          </template>
          <template v-else slot="button-content">
            <i class="fa fa-save mx-2"></i>
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
          block
          variant="info" 
          @click="saveDraft(true)"
        >
          <span v-if="navigationIsExpanded">
            <span class="float-right"><i class="fa fa-save mx-2"></i></span>
            <span class="float-right">Save Draft</span>
          </span>
          <span v-else>
            <i class="fa fa-save mx-2"></i>
          </span>
        </b-button>
        <b-button
          block 
          variant="success" 
          :disabled="!_.isEmpty(errors)"
          @click="submit" 
        >
          <span v-if="navigationIsExpanded">
            <span class="float-right"><i class="fa fa-check mx-2"></i></span>
            <span class="float-right">Submit Request</span>
          </span>
          <span v-else>
            <i class="fa fa-check mx-2"></i>
          </span>
        </b-button>
        <b-button 
          block
          v-b-toggle.my-collapse
          @click="toggleNav()" 
        >
          <span class="when-opened">
            <span class="float-right"><i class="fas fa-angle-double-right mx-2"></i></span>
            <span class="float-right">Toggle Navigation</span>
          </span> 
          <span class="when-closed">
            <i class="fas fa-angle-double-left mx-2"></i>
          </span>
        </b-button>
      </b-button-group>
    </b-nav-form>
    <b-collapse id="my-collapse" visible>
      <hr>
      <b-nav vertical>
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

  export default {
    props: [
      'requestgroup', 
      'errors',
      'draftId'
    ],
    data: function() {
      return {
        navigationIsExpanded: true
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
      toggleNav: function() {
        this.navigationIsExpanded = !this.navigationIsExpanded;
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

  /* Style the dropdowns in this component.*/
  .compose-form-dropdown .dropdown-toggle::before {
    float: left !important;
    margin-top: 0.4rem;
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
  hr {
    width: 100%; 
    height: 1px; 
    border: none;
    background-color: #e4e4e4;
  }
</style>
