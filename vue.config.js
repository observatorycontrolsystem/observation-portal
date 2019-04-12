const path = require('path');
const BundleTracker = require('webpack-bundle-tracker');
const webpack = require('webpack');

// https://cli.vuejs.org/config/
module.exports = {
  outputDir: 'static/bundles',
  publicPath: 'static/bundles',
  lintOnSave: process.env.NODE_ENV !== 'production',
  configureWebpack: config => {

    // Remove the default entry point
    delete config.entry.app;

    return {
      entry: {
        global: './static/js/global',
        compose: './static/js/compose',
        requestgroup_detail: './static/js/requestgroup_detail',
        request_detail: './static/js/request_detail',
        telescope_availability: './static/js/telescope_availability_chart',
        tools: './static/js/tools'
      },
      output: {
        filename: '[name].[hash].js'
      },
      plugins: [
        new BundleTracker({filename: './static/webpack-stats.json'}),
        new webpack.HashedModuleIdsPlugin()
      ],
      optimization: {
        splitChunks: {
          cacheGroups: {
            vendor: {
              test: /[\\/]node_modules[\\/]/,
              name: 'vendor',
              chunks: 'all'
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
