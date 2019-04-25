<template>
    <!-- TODO: make nav collapsible, make it available in the api view, add the detailed error messages as I actually think that its nice, and move
    the buttons into here -->
  <b-navbar sticky v-b-scrollspy>
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
  </b-navbar>
</template>
<script>
  import _ from 'lodash';

  export default {
    props: [
      'requestgroup', 
      'errors'
    ],
    computed: {
      hasRootError: function() {
        return !_.isEmpty(this.errors);
      }
    },
    methods: {
      getErrors: function(path) {
        return _.get(this.errors, path, []);
      },
      hasError: function(path) {
        return !_.isEmpty(this.getErrors(path));
      }
    }
  };
</script>
<style scoped>
  /* Control the nav width for predictability */
  navbar, 
  .nav {
    max-width: 200px;
    min-width: 200px;
    width: 200px;
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
