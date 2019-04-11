var path = require('path');

// https://cli.vuejs.org/config/
module.exports = {
  outputDir: 'static/bundles',
  lintOnSave: process.env.NODE_ENV !== 'production',
  configureWebpack: config => {

    // Remove the default entry point
    delete config.entry.app;

    return {
      entry: {
        global: './static/js/global',
        compose: './static/js/compose',
        userrequest_detail: './static/js/requestgroup_detail',
        request_detail: './static/js/request_detail',
        telescope_availability: './static/js/telescope_availability_chart',
        tools: './static/js/tools'
      },
      output: {
        filename: '[name].js'
      },
      optimization: {
        splitChunks: {
          chunks: 'all',
          cacheGroups: {
            common: {
              name: "common",
              chunks: "initial",
              minChunks: 2
            }
          }
        }
      },
      resolve: {
        alias: {
          // This is needed for jquery-file-download/src/Scripts/jquery.fileDownload.js to work
          'jquery': path.join(__dirname, 'node_modules/jquery/src/jquery')
        }
      }
    };
  }
}
